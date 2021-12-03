#pylint: disable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring
"""
    PhotOS Client

    This client uses the mautrix matrix framework available at:
    https://github.com/mautrix/python

    Parts from this source code are inspired by maubot:
    https://github.com/maubot/maubot
"""
import sys
import os
import asyncio
import traceback
from typing import Dict, Union
from mautrix.client import client as mau
from mautrix.crypto import PgCryptoStateStore, OlmMachine, StateStore as CryptoStateStore, PgCryptoStore
from mautrix.crypto.attachments.attachments import decrypt_attachment
from mautrix.client.state_store.sqlalchemy import SQLStateStore as BaseSQLStateStore
from mautrix.types.event.message import MediaMessageEventContent, TextMessageEventContent
from mautrix.types.primitive import UserID
from mautrix.util.async_db import Database as AsyncDatabase

from mautrix.types import (StrippedStateEvent, Membership,
                           EventType)

class SQLStateStore(BaseSQLStateStore, CryptoStateStore):
    pass

class MissingConfigEntryException(Exception):

    def __init__(self, config_key, message="Missing config entry"):
        self.config_key = config_key
        self.message = f'{message}: {config_key}'
        super().__init__(self.message)

class PhotOsClient():
    '''
        A Simple Matrix client which automatically joins room invitations from trusted users
        and downloads all attachments into a specified folder
    '''

    global_state_store: Union['BaseSQLStateStore', 'CryptoStateStore'] = SQLStateStore()

    @staticmethod
    def get_config_value(config: Dict, key:str):
        if not key in config:
            raise MissingConfigEntryException(key)
        return config[key]


    def __init__(self, config: Dict, client_session, logger) -> None:

        self.user_id = PhotOsClient.get_config_value(config, "user_id")
        self.device_id = PhotOsClient.get_config_value(config, "device_id")
        self.base_url = PhotOsClient.get_config_value(config, "base_url")
        self.database_url = PhotOsClient.get_config_value(config, "database_url")
        self.user_password = PhotOsClient.get_config_value(config, "user_password")
        self.media_path = PhotOsClient.get_config_value(config, "media_path")
        self.trusted_users = PhotOsClient.get_config_value(config, "trusted_users")
        self.media_file = PhotOsClient.get_config_value(config, "media_file")

        self.client_session = client_session
        self.log = logger
        self.crypto_db = None
        self.client = None

    async def initialize(self):
        '''Prepare crypto store and initialize a matrix client'''
        self.crypto_db = AsyncDatabase.create(self.database_url, upgrade_table=PgCryptoStore.upgrade_table)
        crypto_store = PgCryptoStore(account_id=self.user_id, pickle_key="mau.crypto", db=self.crypto_db)
        state_store = PgCryptoStateStore(self.crypto_db)

        self.client = mau.Client(mxid=self.user_id,
                base_url=self.base_url,
                device_id=self.device_id,
                client_session=self.client_session,
                state_store=state_store,
                sync_store=crypto_store,
                log=self.log)

        await self.crypto_db.start()
        await state_store.upgrade_table.upgrade(self.crypto_db)
        await crypto_store.open()

        crypto = OlmMachine(self.client, crypto_store, state_store, self.log)

        self.client.crypto = crypto
        self.client.crypto_log = self.log

        self.client.ignore_first_sync = False
        self.client.ignore_initial_sync = True

        crypto_device_id = await crypto_store.get_device_id()
        if crypto_device_id and crypto_device_id != self.device_id:
            self.log.fatal("Mismatching device ID in crypto store and config "
                      f"(store: {crypto_device_id}, config: {self.device_id})")
            sys.exit(10)

        await self.client.crypto.load()
        if not crypto_device_id:
            await crypto_store.put_device_id(self.device_id)

        if self.client.crypto_enabled:
            self.log.debug("Enabled encryption support")

        login_response = await self.client.login(self.user_id, password=self.user_password)
        self.log.trace(login_response)

        while True:
            try:
                whoami = await self.client.whoami()
            #pylint: disable=broad-except
            except Exception:
                self.log.exception("Failed to connect to homeserver, retrying in 10 seconds...")
                await asyncio.sleep(10)
                continue
            #pylint: enable=broad-except
            if whoami.user_id != self.user_id:
                self.log.fatal(f"User ID mismatch: configured {self.user_id}, but server said {whoami.user_id}")
                sys.exit(11)
            elif whoami.device_id and self.device_id and whoami.device_id != self.device_id:
                self.log.fatal(f"Device ID mismatch: configured {self.device_id}, "
                        f"but server said {whoami.device_id}")
                sys.exit(12)
            self.log.debug(f"Confirmed connection as {whoami.user_id} / {whoami.device_id}")
            break

        self.client.add_event_handler(EventType.ROOM_MEMBER, self._handle_invite)
        self.client.add_event_handler(EventType.ROOM_MESSAGE, self._handle_message)

    async def _handle_invite(self, evt: StrippedStateEvent) -> None:
        self.log.trace('_handle_invite')
        self.log.trace(evt.state_key)

        if evt.state_key == self.user_id and self.is_trusted_user(evt.sender) and evt.content.membership == Membership.INVITE:
            self.log.debug('join room!')
            await self.client.join_room(evt.room_id)

        if evt.state_key == self.user_id and not self.is_trusted_user(evt.sender) and evt.content.membership == Membership.INVITE:
            self.log.trace(f'untrusted user {evt.sender}')

    def is_trusted_user(self, user_id: UserID) -> bool:
        if not user_id:
            return False

        return user_id in self.trusted_users

    def _get_next_filename(self, prefered_filename: str, index: int=0) -> str:
        suffix = f" #{index}" if index > 0 else ''
        new_filename = f'{prefered_filename}{suffix}'
        if os.path.exists(new_filename):
            return self._get_next_filename(prefered_filename, index+1)
        return new_filename

    async def _store_data(self, media_content: MediaMessageEventContent) -> None:
        target = self._get_next_filename(os.path.join(self.media_path, str(media_content.body)))
        encrypted_data = await self.client.download_media(media_content.file.url)

        file_hash = media_content.file.hashes['sha256']
        vector = media_content.file.iv
        decrypted_data = decrypt_attachment(encrypted_data, media_content.file.key.key, file_hash, vector)

        #TODO maybe store the hash somewhere and only store the file if we dont have a file with the same hash

        self.log.trace(f'save file as {target}')
        with open(target, "wb") as binary_file:
            binary_file.write(decrypted_data)
            self._add_to_media_file(target)

    def _add_to_media_file(self, filename) -> None:
        with open(self.media_file, 'a', encoding='utf-8') as binary_file:
            binary_file.writelines([filename])

    async def _handle_message(self, evt: StrippedStateEvent) -> None:
        self.log.trace('_handle_message')

        try:
            if isinstance(evt.content, TextMessageEventContent):
                self.log.trace('TextMessageEventContent')
                print(evt.content.body)

            if isinstance(evt.content, MediaMessageEventContent):
                self.log.trace('MediaMessageEventContent')
                await self._store_data(evt.content)

        #pylint: disable=broad-except
        except Exception as error:
            self.log.error(error)
            traceback.print_exc()
        #pylint: enable=broad-except

    async def stop(self):
        self.client.stop()
        await self.crypto_db.stop()
        await self.client.logout()
        self.log.info('client stopped!')

    async def start(self):
        self.log.info('starting client')
        self.client.start(None)
#pylint: enable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring
