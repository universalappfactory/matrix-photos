#pylint: disable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring
import os
from enum import Enum
from typing import Dict, List, Tuple
from mautrix.types.event.message import MessageType, TextMessageEventContent
from .utils import get_config_value

class AdminCommands(str, Enum):
    HELP = '!help'
    REREAD = '!reread'

    @staticmethod
    def list():
        return list(map(lambda c: c.value, AdminCommands))

    @staticmethod
    def get_description(command):
        if command == AdminCommands.HELP:
            return f'{command} - shows this message'
        if command == AdminCommands.REREAD:
            return f'{command} - reread directory with images and create image text files'

    @staticmethod
    def help_message():
        return list(map(AdminCommands.get_description, AdminCommands))

class AdminCommandHandler:

    def __init__(self, admin_user: str, config: Dict, logger) -> None:
        self.log = logger
        self.admin_user = admin_user
        self.media_path = get_config_value(config, "media_path")
        self.media_file = get_config_value(config, "media_file")
        self.max_file_count = int(get_config_value(config, "max_file_count"))
        self.complete_media_file = get_config_value(config, "complete_media_file", False)

    def _create_help_message(self) -> str:
        return "\n".join(AdminCommands.help_message())

    @staticmethod
    def _is_file(file: str):
        if not file.endswith('.txt'):
            return os.path.isfile(file)

    def _reread_files(self) -> str:
        file_list = sorted(filter(AdminCommandHandler._is_file, map(lambda f: os.path.join(self.media_path, f), os.listdir(self.media_path))), key=os.path.getmtime)

        with open(self.media_file, 'w+', encoding='utf-8') as text_file:
            new_data =  map(lambda f: f'{f}\n', file_list[-self.max_file_count:])
            text_file.writelines(new_data)

        if self.complete_media_file:
            with open(self.complete_media_file, 'w+', encoding='utf-8') as text_file:
                new_data =  map(lambda f: f'{f}\n', file_list)
                text_file.writelines(new_data)

        return "Done reread files"

    def _handle_command(self, command: str, params: List) -> str:
        self.log.trace(f'_handle_command: {command}')
        self.log.trace(params)
        try:
            if command == AdminCommands.REREAD:
                return self._reread_files()
            if command == AdminCommands.HELP:
                return self._create_help_message()
        except Exception as exception:
            return str(exception)

        return None

    def _get_command_with_parameters(self, content: TextMessageEventContent) -> Tuple[str, List[str]]:
        commands = content.body.split(' ')
        if len(commands) <= 0:
            self.log.trace("no commands given")
            return None

        return (commands[0], commands[1:] if len(commands) > 1 else [])

    def is_admin_command(self, content: TextMessageEventContent):
        if content.msgtype == MessageType.TEXT:
            commands = self._get_command_with_parameters(content)
            if commands:
                return commands[0].startswith("!")

        return False

    def handle(self, content: TextMessageEventContent):
        self.log.trace('handle admincommand')
        if self.is_admin_command(content):
            commands = self._get_command_with_parameters(content)
            return self._handle_command(commands[0], commands[1])

        return None
#pylint: enable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring
