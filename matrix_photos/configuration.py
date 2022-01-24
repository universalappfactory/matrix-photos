from typing import List, NamedTuple, Dict


class ConvertConfiguration(NamedTuple):
    convert_on_save: bool
    convert_binary: str
    convert_parameters: List[str]


class MessageConvertConfiguration(NamedTuple):
    write_text_messages: bool
    convert_binary: str
    convert_text_parameter: str
    convert_parameters: List[str]


class MatrixConfiguration(NamedTuple):
    user_id: str
    user_password: str
    device_id: str
    base_url: str
    database_url: str
    media_path: str
    media_file: str
    complete_media_file: str
    min_free_disk_space_mb: str
    max_file_count: int
    max_download_size_mb: int
    admin_user: str
    trusted_users: str
    convert: ConvertConfiguration
    message_convert: MessageConvertConfiguration
    allowed_mimetypes: List[str]
    random_response_messages: List[str]

    @staticmethod
    def from_dict(data: Dict):
        clone = dict(data)
        convert_dict = clone.pop('convert')
        convert = ConvertConfiguration(**convert_dict)
        message_convert_dict = clone.pop('message_convert')
        message_convert = MessageConvertConfiguration(**message_convert_dict)
        return MatrixConfiguration(**clone, convert=convert, message_convert=message_convert)
