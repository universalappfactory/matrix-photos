from unittest import TestCase
import os
import yaml
from matrix_photos.configuration import MatrixConfiguration


class TestModels(TestCase):

    def test_that_configuration_is_deserialized_as_expected(self):
        example_config_file = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                           "..",
                                                           "matrix_photos",
                                                           "config-example.yml"))

        with open(example_config_file, 'r', encoding='utf-8') as stream:
            data = yaml.load(stream, Loader=yaml.SafeLoader)
            loaded_matrix_configuration = data['matrix']

            matrix_configuration = MatrixConfiguration.from_dict(loaded_matrix_configuration)
            self.assertIsNotNone(matrix_configuration)

            configuration_as_dictionary = matrix_configuration._asdict()
            convert = configuration_as_dictionary.pop('convert')
            matrix_convert = configuration_as_dictionary.pop('message_convert')

            configuration_as_dictionary['convert'] = convert._asdict()
            configuration_as_dictionary['message_convert'] = matrix_convert._asdict()

            self.assertDictEqual(loaded_matrix_configuration,
                                 configuration_as_dictionary)

    def test_that_properties_of_child_objects_can_be_accessed(self):
        example_config_file = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                           "..",
                                                           "matrix_photos",
                                                           "config-example.yml"))

        with open(example_config_file, 'r', encoding='utf-8') as stream:
            data = yaml.load(stream, Loader=yaml.SafeLoader)
            loaded_matrix_configuration = data['matrix']

            matrix_configuration = MatrixConfiguration.from_dict(loaded_matrix_configuration)
            self.assertIsNotNone(matrix_configuration)
            self.assertEqual(matrix_configuration.convert.convert_binary, '/usr/bin/convert')
            