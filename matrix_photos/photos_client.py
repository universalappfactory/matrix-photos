#pylint: disable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring
"""
    PhotOS Client

    This client uses the mautrix matrix framework available at:
    https://github.com/mautrix/python

    Parts from this source code are inspired by maubot:
    https://github.com/maubot/maubot
"""
import sys
import asyncio
import traceback
import random
from typing import Dict, Union
from mautrix.client import client as mau
from mautrix.crypto import PgCryptoStateStore, OlmMachine, StateStore as CryptoStateStore, PgCryptoStore
from mautrix.crypto.attachments.attachments import decrypt_attachment
from mautrix.client.state_store.sqlalchemy import SQLStateStore as BaseSQLStateStore
from mautrix.types.event.encrypted import EncryptedEvent
from mautrix.types.event.message import MediaMessageEventContent, MessageType, TextMessageEventContent
from mautrix.types.misc import PaginationDirection
from mautrix.types.primitive import RoomID, UserID
from mautrix.util.async_db import Database as AsyncDatabase

from mautrix.types import (StrippedStateEvent, Membership,
                           EventType)

from matrix_photos.text_message_command_handler import TextmessageCommandHandler

from .storage_strategy import DefaultStorageStrategy
from .utils import get_config_value
from .admin_command_handler import AdminCommandHandler
from .text_message_command_handler import TextmessageCommandHandler


class SQLStateStore(BaseSQLStateStore, CryptoStateStore):
    pass

class PhotOsClient():
    '''
        A Simple Matrix client which automatically joins room invitations from trusted users
        and downloads all attachments into a specified folder
    '''

    global_state_store: Union['BaseSQLStateStore', 'CryptoStateStore'] = SQLStateStore()

    def __init__(self, config: Dict, client_session, logger) -> None:

        self.user_id = get_config_value(config, "user_id")
        self.device_id = get_config_value(config, "device_id")
        self.base_url = get_config_value(config, "base_url")
        self.database_url = get_config_value(config, "database_url")
        self.user_password = get_config_value(config, "user_password")
        self.media_path = get_config_value(config, "media_path")
        self.trusted_users = get_config_value(config, "trusted_users")
        self.media_file = get_config_value(config, "media_file")
        self.client_session = client_session
        self.log = logger
        self.storage_strategy = DefaultStorageStrategy(config, logger)
        self.admin_user = get_config_value(config, "admin_user", False)
        self.allowed_mimetypes = get_config_value(config, "allowed_mimetypes", False)
        if self.admin_user:
            self.admin_command_handler = AdminCommandHandler(self.admin_user, config, logger)

        self.text_message_command_handler = TextmessageCommandHandler(config, logger)
        self.random_response_messages = get_config_value(config, "random_response_messages", False)

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
        self.client.ignore_initial_sync = False

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

    def is_admin_user(self, user_id: UserID) -> bool:
        return user_id == self.admin_user

    async def _store_data(self, media_content: MediaMessageEventContent) -> None:
        encrypted_data = await self.client.download_media(media_content.file.url)

        file_hash = media_content.file.hashes['sha256']
        vector = media_content.file.iv
        decrypted_data = decrypt_attachment(encrypted_data, media_content.file.key.key, file_hash, vector)

        #IDEA maybe store the hash somewhere and only store the file if we dont have a file with the same hash
        self.storage_strategy.store(decrypted_data, str(media_content.body))


    def _is_allowed_content(self, content: MediaMessageEventContent):
        result = content.info.mimetype in self.allowed_mimetypes
        if not result:
            self.log.warn(f'mimetype not allowed: {content.info.mimetype}')
        return result

    async def _handle_admin_command(self, evt: StrippedStateEvent):
        if self.admin_command_handler:
            response = self.admin_command_handler.handle(evt.content)
            if response:
                content = TextMessageEventContent(MessageType.TEXT, response)
                content.set_reply(evt)
                await self.client.send_message_event(evt.room_id, EventType.ROOM_MESSAGE, content)

    def _is_admin_command(self, evt: StrippedStateEvent) -> bool:
        if self.is_admin_user(evt.sender) and self.admin_command_handler:
            return self.admin_command_handler.is_admin_command(evt.content)

        return False

    async def _handle_message_event(self, evt: StrippedStateEvent) -> None:
        if self._is_admin_command(evt):
            await self._handle_admin_command(evt)
        else:
            is_foreign_message = evt.sender != self.user_id
            media_message_before = await self.message_before_was_media_message(evt.room_id)
            if is_foreign_message and media_message_before:
                self.text_message_command_handler.handle(evt.content)


    async def message_before_was_media_message(self, room_id: RoomID) -> bool:
        token = await self.client.sync_store.get_next_batch()
        if token:
            messages = await self.client.get_messages(room_id, direction=PaginationDirection.BACKWARD, from_token=token, limit=10)
            foreign_messages = list(filter(lambda x: x.sender != self.user_id, messages.events))[:2]

            if len(foreign_messages) == 2:
                event = foreign_messages[1]
                if isinstance(event, EncryptedEvent):
                    decrypted = await self.client.crypto.decrypt_megolm_event(event)
                    if decrypted and isinstance(decrypted.content, MediaMessageEventContent):
                        return True
        return False

    async def _send_random_response_message(self, evt: StrippedStateEvent):
        if not self.random_response_messages:
            return

        response = random.choice(self.random_response_messages)
        content = TextMessageEventContent(MessageType.TEXT, response)
        content.set_reply(evt)
        await self.client.send_message_event(evt.room_id, EventType.ROOM_MESSAGE, content)

    async def _handle_message(self, evt: StrippedStateEvent) -> None:
        self.log.trace('_handle_message')

        try:
            if isinstance(evt.content, TextMessageEventContent):
                self.log.trace('TextMessageEventContent')
                await self._handle_message_event(evt)

            if isinstance(evt.content, MediaMessageEventContent) and self._is_allowed_content(evt.content):
                self.log.trace('MediaMessageEventContent')
                await self._store_data(evt.content)
                await self._send_random_response_message(evt)

        #pylint: disable=broad-except
        except Exception as error:
            self.log.error(error)
            traceback.print_exc()
        #pylint: enable=broad-except

    async def stop(self):
        self.client.stop()
        await self.crypto_db.stop()
        self.log.info('client stopped!')

    async def start(self):
        self.log.info('starting client')
        self.client.start(None)
#pylint: enable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring
