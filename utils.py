import os

import boto3

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


def to_canonical_region_name(region):
    """
    In AWS, region names can be either us-west-1 or us-west-1b; when using an Availability zone,
    we want the more detailed version, but when playing with general ec2 interface, it needs to be the general name
    :param region:
    :return:
    """
    if region.endswith('a') or region.endswith('b'):
        return region[:-1]
    return region


def create_keyfile(name, region):
    """
    Creates a key pair in AWS and saves the .pem file to default location,
    so that the user can connect to the instance using SSH
    :param name: the key name
    :param region: the region where the key should be created
    :return: the full key path
    """
    ec2 = boto3.resource('ec2', region_name=region)
    keyfile = name + ".pem"
    key = ec2.create_key_pair(KeyName=name)
    full_keyfile = os.path.join(DEFAULT_FILES_LOCATION, keyfile)
    with open(full_keyfile, 'w') as f:
        f.write(key.key_material)
    os.chmod(full_keyfile, 0o600)
    return full_keyfile
