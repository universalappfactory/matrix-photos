#pylint: disable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring
from typing import Dict

class MissingConfigEntryException(Exception):

    def __init__(self, config_key, message="Missing config entry"):
        self.config_key = config_key
        self.message = f'{message}: {config_key}'
        super().__init__(self.message)

class EmptyConfigEntryException(Exception):

    def __init__(self, config_key, message="Empty config entry"):
        self.config_key = config_key
        self.message = f'{message}: {config_key}'
        super().__init__(self.message)

def get_config_value(config: Dict, key:str, required: bool=True):
    if not key in config:
        if not required:
            return None
        raise MissingConfigEntryException(key)

    value = config[key]
    if isinstance(value, str):
        value = value.strip()
        if len(value) <= 0:
            raise EmptyConfigEntryException(key)

    return value
#pylint: enable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring
