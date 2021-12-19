#pylint: disable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring, broad-except
import subprocess

class FileConvert:

    def __init__(self, convert_binary: str, logger) -> None:
        self.log = logger
        self.convert_binary = convert_binary

    def convert_file(self, filename, convert_params, message=None, convert_text_parameter: str=None):
        try:
            self.log.trace(f'convert_file {filename}')

            text = []

            if message:
                msg = f"'{message}'"
                text.append(f'{convert_text_parameter} {msg}')

            params = [
                self.convert_binary,
                *convert_params,
                *text,
                f'{filename}',
                f'{filename}'
                ]

            result = subprocess.run(params, capture_output=True, text=True, check=True)
            self.log.trace(result.stdout)
            self.log.trace(result.stderr)
        except Exception as error:
            self.log.error(error)
#pylint: enable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring, broad-except
