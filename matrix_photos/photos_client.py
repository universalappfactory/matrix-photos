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
from typing import Union
from mautrix.client import client as mau
from mautrix.client.dispatcher import SimpleDispatcher
from mautrix.client.encryption_manager import DecryptionDispatcher

from mautrix.crypto import (
    PgCryptoStateStore,
    OlmMachine,
    StateStore as CryptoStateStore,
    PgCryptoStore
)
from mautrix.crypto.attachments.attachments import decrypt_attachment
from mautrix.client.state_store.sqlalchemy import SQLStateStore as BaseSQLStateStore
from mautrix.types.event.encrypted import EncryptedEvent
from mautrix.types.event.message import (MediaMessageEventContent,
                                         MessageType,
                                         TextMessageEventContent
                                         )
from mautrix.types.misc import PaginationDirection
from mautrix.types.primitive import RoomID, UserID
from mautrix.util.async_db import Database as AsyncDatabase
from mautrix.types import (StrippedStateEvent,
                           Membership,
                           EventType
                           )

from mautrix.errors import DecryptionError
from matrix_photos.text_message_command_handler import TextmessageCommandHandler
from .storage_strategy import DefaultStorageStrategy
from .admin_command_handler import AdminCommandHandler
from .text_message_command_handler import TextmessageCommandHandler
from .configuration import MatrixConfiguration


class SQLStateStore(BaseSQLStateStore, CryptoStateStore):
    pass
class ClientDecryptionDispatcher(SimpleDispatcher):
    """
    This is a custom decryption dispatcher which sends a m.room_key_request to-device event
    when decryption fails in order to try decryption again.
    """

    #pylint: disable=no-member
    event_type = EventType.ROOM_ENCRYPTED
    #pylint: enable=no-member
    client: mau.Client
    user_id = ""

    async def _request_room_key_for_event(self, evt: EncryptedEvent):
        try:
            self.client.crypto_log.trace("request room keys")
            await self.client.crypto.request_room_key(
                evt.room_id,
                evt.content.sender_key,
                evt.content.session_id,
                from_devices={evt.sender: [evt.content.device_id]}, timeout=10)
        #pylint:disable=broad-except
        except Exception as error:
            self.client.crypto_log.error(error)
        #pylint:enable=broad-except

    async def _retry_handle_event(self, evt: EncryptedEvent):
        try:
            self.client.crypto_log.trace("retry to handle event")
            await self._handle_event(evt)
        #pylint:disable=broad-except
        except Exception as retry_error:
            self.client.crypto_log.error("failed to retry", retry_error)
        #pylint:enable=broad-except

    async def _handle_event(self, evt: EncryptedEvent) -> None:
        decrypted = await self.client.crypto.decrypt_megolm_event(evt)
        self.client.dispatch_event(decrypted, evt.source)

    async def handle(self, evt: EncryptedEvent) -> None:
        try:
            self.client.crypto_log.trace(
                f'try to decrypt event {evt.event_id}')
            await self._handle_event(evt)
        except DecryptionError as error:
            self.client.crypto_log.warn(
                'decryption error, try to request room keys', error)
            await self._request_room_key_for_event(evt)
            await self._retry_handle_event(evt)


class PhotOsClient():
    '''
        A Simple Matrix client which automatically joins room invitations from trusted users
        and downloads all attachments into a specified folder
    '''

    global_state_store: Union['BaseSQLStateStore',
                              'CryptoStateStore'] = SQLStateStore()

    def __init__(self, config: MatrixConfiguration, client_session, logger) -> None:
        self._config = config
        self.client_session = client_session
        self.log = logger
        self.storage_strategy = DefaultStorageStrategy(config, logger)

        if self._config.admin_user:
            self.admin_command_handler = AdminCommandHandler(config, logger)

        self.text_message_command_handler = TextmessageCommandHandler(
            config, logger)

        self.crypto_db = None
        self.client = None

    async def _get_valid_device_id(self, crypto_store: PgCryptoStore) -> None:
        crypto_device_id = await crypto_store.get_device_id()
        if crypto_device_id and crypto_device_id != self._config.device_id:
            self.log.warn("Mismatching device ID in crypto store and config "
                          f"(store: {crypto_device_id}, config: {self._config.device_id})"
                          "add new device_id")
            await crypto_store.put_device_id(self._config.device_id)

        return await crypto_store.get_device_id()

    async def initialize(self):
        '''Prepare crypto store and initialize a matrix client'''
        self.crypto_db = AsyncDatabase.create(
            self._config.database_url, upgrade_table=PgCryptoStore.upgrade_table)
        crypto_store = PgCryptoStore(
            account_id=self._config.user_id, pickle_key="mau.crypto", db=self.crypto_db)
        state_store = PgCryptoStateStore(self.crypto_db)

        self.client = mau.Client(mxid=self._config.user_id,
                                 base_url=self._config.base_url,
                                 device_id=self._config.device_id,
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

        crypto_device_id = await self._get_valid_device_id(crypto_store)
        await self.client.crypto.load()
        if not crypto_device_id:
            await crypto_store.put_device_id(self._config.device_id)

        if self.client.crypto_enabled:
            self.log.debug("Enabled encryption support")

        self.client.remove_dispatcher(DecryptionDispatcher)
        ClientDecryptionDispatcher.user_id = self._config.user_id
        self.client.add_dispatcher(ClientDecryptionDispatcher)

        login_response = await self.client.login(self._config.user_id,
                                                 password=self._config.user_password)
        self.log.trace(login_response)

        while True:
            try:
                whoami = await self.client.whoami()
            # pylint: disable=broad-except
            except Exception:
                self.log.exception(
                    "Failed to connect to homeserver, retrying in 10 seconds...")
                await asyncio.sleep(10)
                continue
            # pylint: enable=broad-except
            if whoami.user_id != self._config.user_id:
                # pylint: disable=line-too-long
                self.log.fatal(
                    f"User ID mismatch: configured {self._config.user_id}, but server said {whoami.user_id}"
                )
                sys.exit(11)
            elif whoami.device_id and self._config.device_id and whoami.device_id != self._config.device_id:
                self.log.fatal(f"Device ID mismatch: configured {self._config.device_id}, "
                               f"but server said {whoami.device_id}")
                sys.exit(12)
                # pylint: enable=line-too-long
            self.log.debug(
                f"Confirmed connection as {whoami.user_id} / {whoami.device_id}")
            break

        #pylint: disable=no-member
        self.client.add_event_handler(
            EventType.ROOM_MEMBER, self._handle_invite)
        self.client.add_event_handler(
            EventType.ROOM_MESSAGE, self._handle_message)
        #pylint: enable=no-member

    async def _handle_invite(self, evt: StrippedStateEvent) -> None:
        self.log.trace('_handle_invite')
        self.log.trace(evt.state_key)

        if (evt.state_key == self._config.user_id
                    and self.is_trusted_user(evt.sender)
                    and evt.content.membership == Membership.INVITE
                ):
            self.log.debug('join room!')
            await self.client.join_room(evt.room_id)

        if (evt.state_key == self._config.user_id
                and not self.is_trusted_user(evt.sender)
                and evt.content.membership == Membership.INVITE
            ):
            self.log.trace(f'untrusted user {evt.sender}')

    def is_trusted_user(self, user_id: UserID) -> bool:
        if not user_id:
            return False

        return user_id in self._config.trusted_users

    def is_admin_user(self, user_id: UserID) -> bool:
        return user_id == self._config.admin_user

    def max_download_size_exceeded(self, media_content: MediaMessageEventContent) -> bool:
        media_size = media_content.info.size
        return self._config.max_download_size_mb < media_size / (1024*1024)

    async def _store_data(self, media_content: MediaMessageEventContent) -> bool:
        if self.max_download_size_exceeded(media_content):
            self.log.warn('max download size exceeded')
            return False

        if not media_content.file:
            self.log.error(
                'mediamessage does not contain encrypted data, is encryption enabled in your room?')
            return False

        encrypted_data = await self.client.download_media(media_content.file.url)

        file_hash = media_content.file.hashes['sha256']
        vector = media_content.file.iv
        decrypted_data = decrypt_attachment(
            encrypted_data, media_content.file.key.key, file_hash, vector)

        # IDEA maybe store the hash somewhere and only store the file
        # if we dont have a file with the same hash
        self.storage_strategy.store(decrypted_data, str(media_content.body))
        return True

    def _is_allowed_content(self, content: MediaMessageEventContent):
        result = content.info.mimetype in self._config.allowed_mimetypes
        if not result:
            self.log.warn(f'mimetype not allowed: {content.info.mimetype}')
        return result

    async def _handle_admin_command(self, evt: StrippedStateEvent):
        if self.admin_command_handler:
            response = self.admin_command_handler.handle(evt.content)
            if response:
                #pylint: disable=no-member, too-many-function-args
                content = TextMessageEventContent(MessageType.TEXT, response)
                content.set_reply(evt)
                await self.client.send_message_event(evt.room_id, EventType.ROOM_MESSAGE, content)
                #pylint: enable=no-member, too-many-function-args

    def _is_admin_command(self, evt: StrippedStateEvent) -> bool:
        if self.is_admin_user(evt.sender) and self.admin_command_handler:
            return self.admin_command_handler.is_admin_command(evt.content)

        return False

    async def _handle_message_event(self, evt: StrippedStateEvent) -> None:
        if self._is_admin_command(evt):
            await self._handle_admin_command(evt)
        else:
            is_foreign_message = evt.sender != self._config.user_id
            media_message_before = await self.message_before_was_media_message(evt.room_id,
                                                                               evt.sender)
            if is_foreign_message and media_message_before:
                self.text_message_command_handler.handle(evt.content)

    async def message_before_was_media_message(self, room_id: RoomID, sender_id: UserID) -> bool:
        token = await self.client.sync_store.get_next_batch()
        if token:
            # pylint:disable=fixme
            # When https://github.com/mautrix/python/issues/87 is released

            # sender_filter =
            # f'{{"lazy_load_members":true,"limit":2,"senders":["{sender_id}"],
            # "not_senders":["{self.user_id}"]}}'
            # self.log.trace(sender_filter)
            # pylint:enable=fixme

            messages = await self.client.get_messages(room_id,
                                                      direction=PaginationDirection.BACKWARD,
                                                      from_token=token,
                                                      limit=20)
            sender_messages = list(
                filter(lambda x: x.sender == sender_id, messages.events))[:2]

            if len(sender_messages) == 2:
                event = sender_messages[1]
                if isinstance(event, EncryptedEvent):
                    decrypted = await self.client.crypto.decrypt_megolm_event(event)
                    if decrypted and isinstance(decrypted.content, MediaMessageEventContent):
                        return True
        return False

    async def _send_random_response_message(self, evt: StrippedStateEvent):
        if not self._config.random_response_messages:
            return
        #pylint: disable=no-member, too-many-function-args
        response = random.choice(self._config.random_response_messages)
        content = TextMessageEventContent(MessageType.TEXT, response)
        content.set_reply(evt)
        await self.client.send_message_event(evt.room_id, EventType.ROOM_MESSAGE, content)
        #pylint: enable=no-member, too-many-function-args

    async def _send_reply_text_message(self, evt: StrippedStateEvent, response_text: str):
        #pylint: disable=no-member, too-many-function-args
        content = TextMessageEventContent(MessageType.TEXT, response_text)
        content.set_reply(evt)
        await self.client.send_message_event(evt.room_id, EventType.ROOM_MESSAGE, content)
        #pylint: enable=no-member, too-many-function-args

    async def _handle_message(self, evt: StrippedStateEvent) -> None:
        self.log.trace('_handle_message')

        try:
            if isinstance(evt.content, TextMessageEventContent):
                self.log.trace('TextMessageEventContent')
                await self._handle_message_event(evt)

            if (isinstance(evt.content, MediaMessageEventContent)
                and self._is_allowed_content(evt.content)
                ):
                self.log.trace('MediaMessageEventContent')
                if await self._store_data(evt.content):
                    await self._send_random_response_message(evt)
                else:
                    await self._send_reply_text_message(evt, "your file has been revoked.")

        # pylint: disable=broad-except
        except Exception as error:
            self.log.error(error)
            traceback.print_exc()
        # pylint: enable=broad-except

    async def stop(self):
        self.client.stop()
        await self.crypto_db.stop()
        self.log.info('client stopped!')

    async def start(self):
        self.log.info('starting client')
        self.client.start(None)
