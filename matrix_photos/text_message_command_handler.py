#pylint: disable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring, broad-except
import subprocess
from typing import Dict
from mautrix.types.event.message import MessageType, TextMessageEventContent
from .utils import get_config_value
from .file_convert import FileConvert
class TextmessageCommandHandler:

    def __init__(self, config: Dict, logger) -> None:
        self.log = logger
        self.write_text_messages = get_config_value(config["message_convert"], "write_text_messages")
        self.convert_parameters = get_config_value(config["message_convert"], "convert_parameters")
        self.convert_text_parameter = get_config_value(config["message_convert"], "convert_text_parameter")
        self.media_file = get_config_value(config, "media_file")
        self._convert = FileConvert(get_config_value(config["message_convert"], "convert_binary"), logger)

    def _get_last_filename(self):
        file_data = []
        try:
            with open(self.media_file, 'r', encoding='utf-8') as text_file:
                file_data = text_file.readlines()
                return file_data[-1]
        except IOError:
            pass
        return ""

    # ToDo better exception handling when command fails
    def _add_message_to_file(self, filename, message):
        self.log.trace(f'_add_text_to_file {message}')
        self._convert.convert_file(filename, self.convert_parameters, message=message, convert_text_parameter=self.convert_text_parameter)

    def _handle_text_message(self, content: TextMessageEventContent):
        target_filename = str(self._get_last_filename()).strip()
        self.log.trace('_handle_text_message')
        if target_filename:
            self._add_message_to_file(target_filename, content.body)

    def handle(self, content: TextMessageEventContent):
        try:
            if content.msgtype == MessageType.TEXT and not content.body.startswith('!') and self.write_text_messages:
                return self._handle_text_message(content)

            return None
        except Exception as error:
            self.log.error(error)
            return None
#pylint: enable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring, broad-except
