from mautrix.types.event.message import MessageType, TextMessageEventContent
from .file_convert import FileConvert
from .configuration import MatrixConfiguration


class TextmessageCommandHandler:

    def __init__(self, config: MatrixConfiguration, logger) -> None:
        self.log = logger
        self._config = config
        self._convert = FileConvert(
            config.message_convert.convert_binary, logger)

    def _get_last_filename(self):
        file_data = []
        try:
            with open(self._config.media_file, 'r', encoding='utf-8') as text_file:
                file_data = text_file.readlines()
                return file_data[-1]
        except IOError:
            pass
        return ""

    #pylint: disable=fixme, line-too-long
    # ToDo better exception handling when command fails
    def _add_message_to_file(self, filename, message):
        self.log.trace(f'_add_text_to_file {message}')
        self._convert.convert_file(filename,
                                   self._config.message_convert.convert_parameters,
                                   message=message,
                                   convert_text_parameter=self._config.message_convert.convert_text_parameter
                                   )
    #pylint: enable=fixme, line-too-long

    def _handle_text_message(self, content: TextMessageEventContent):
        target_filename = str(self._get_last_filename()).strip()
        self.log.trace('_handle_text_message')
        if target_filename:
            self._add_message_to_file(target_filename, content.body)

    def handle(self, content: TextMessageEventContent):
        try:
            if (content.msgtype == MessageType.TEXT
                and not content.body.startswith('!')
                    and self._config.message_convert.write_text_messages):
                return self._handle_text_message(content)

            return None
        # pylint: disable=broad-except
        except Exception as error:
            self.log.error(error)
            return None
        # pylint: enable=broad-except
