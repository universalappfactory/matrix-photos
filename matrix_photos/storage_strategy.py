import os
from pathlib import Path
from .utils import reread_files, disk_usage, get_media_file_list
from .configuration import MatrixConfiguration
from .file_convert import FileConvert


class DefaultStorageStrategy():
    """
    stores the latest {max_file_count} pictures in the {media_file} textfile
    all other pictures are written to the {complete_media_file} textfile
    """

    def __init__(self, config: MatrixConfiguration, logger) -> None:
        self._config = config
        self.log = logger
        self._convert = FileConvert(config.convert.convert_binary, logger)
        
        try:
            Path("/data/photoframe/images_local").mkdir(parents=False, exist_ok=False)
            self.log.warning('created local image directory /data/photoframe/images_local since it was not found')
        except FileNotFoundError as e:
            self.log.error('failed to create local image directory at /data/photoframe, probably missing parent directory')
            raise e
        except FileExistsError:
            self.log.trace('local image directory found')

    def _append_to_complete_media_file(self, filename) -> None:
        if not self._config.complete_media_file:
            return

        with open(self._config.complete_media_file, 'a', encoding='utf-8') as binary_file:
            binary_file.write(f'{filename}\n')

    def _add_to_media_file(self, filename) -> None:
        file_data = []
        try:
            with open(self._config.media_file, 'r', encoding='utf-8') as text_file:
                file_data = text_file.readlines()
        except IOError:
            pass

        file_data.append(f'{filename}\n')
        with open(self._config.media_file, 'w+', encoding='utf-8') as text_file:
            new_data = file_data[-self._config.max_file_count:]
            text_file.writelines(new_data)

    def _get_next_filename(self, prefered_filename: str, index: int = 0) -> str:
        (base, ext) = os.path.splitext(prefered_filename)
        new_filename = prefered_filename
        index = 1
        while os.path.exists(new_filename):
            new_filename = f'{base}#{index}{ext}'
            index += 1
        return new_filename

    def _convert_file(self, filename: str):
        self._convert.convert_file(
            filename, self._config.convert.convert_parameters)

    def _delete_eldest_file(self):
        try:
            file_list = get_media_file_list(self._config.media_path)
            if len(file_list) > 0:
                file_to_delete = file_list[0]
                os.remove(file_to_delete)
        # pylint: disable=broad-except
        except Exception as error:
            self.log.error(error)
        # pylint: enable=broad-except

    def _delete_eldest_files(self):
        free_space_mb = disk_usage(
            self._config.media_path).free / (1024 * 1024)
        if ((self._config.min_free_disk_space_mb > 0)
                and self._config.min_free_disk_space_mb > free_space_mb
            ):
            self._delete_eldest_file()
            self._delete_eldest_files()

    def _check_storage_limit(self):
        free_space_mb = disk_usage(
            self._config.media_path).free / (1024 * 1024)
        if ((self._config.min_free_disk_space_mb > 0)
                and self._config.min_free_disk_space_mb > free_space_mb
                ):
            self._delete_eldest_files()
            reread_files(self._config.media_path,
                         self._config.media_file,
                         self._config.complete_media_file,
                         self._config.max_file_count)

    def store(self, data: bytes, filename: str) -> None:
        target = self._get_next_filename(
            os.path.join(self._config.media_path, filename))

        self._check_storage_limit()

        self.log.trace(f'save file as {target}')
        with open(target, "wb") as binary_file:
            binary_file.write(data)
            binary_file.close()

        if self._config.convert.convert_on_save:
            self._convert_file(target)

        self._add_to_media_file(target)
        self._append_to_complete_media_file(target)
