import os

from settings import DEFAULT_FILES_LOCATION


def get_shh_key_file(filename):
    """
    A helper funtion which allows to find an SSH key file using the filename
    :param filename:
    :return: a full path of the key
    """
    if not filename.endswith(".pem"):
        filename = filename + ".pem"

    full_filepath = os.path.join(DEFAULT_FILES_LOCATION, filename)
    if not os.path.exists(full_filepath):
        raise Exception("Key file {} missing".format(full_filepath))
    return full_filepath
