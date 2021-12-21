#pylint: disable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring
import os
from typing import Dict
from collections import namedtuple

DiskUsage = namedtuple('DiskUsage', 'total used free')
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

def disk_usage(path):
    stats = os.statvfs(path)
    free = stats.f_bavail * stats.f_frsize
    total = stats.f_blocks * stats.f_frsize
    used = (stats.f_blocks - stats.f_bfree) * stats.f_frsize
    return DiskUsage(total, used, free)

def is_file(file: str):
    if not file.endswith('.txt'):
        return os.path.isfile(file)

def get_media_file_list(media_path: str):
    return sorted(filter(is_file, map(lambda f: os.path.join(media_path, f), os.listdir(media_path))), key=os.path.getmtime)

def reread_files(media_path: str, media_file: str, complete_media_file: str, max_file_count: int) -> str:
    file_list = get_media_file_list(media_path)

    with open(media_file, 'w+', encoding='utf-8') as text_file:
        new_data =  map(lambda f: f'{f}\n', file_list[-max_file_count:])
        text_file.writelines(new_data)

    if complete_media_file:
        with open(complete_media_file, 'w+', encoding='utf-8') as text_file:
            new_data =  map(lambda f: f'{f}\n', file_list)
            text_file.writelines(new_data)

#pylint: enable=missing-module-docstring, missing-function-docstring, line-too-long, missing-class-docstring
