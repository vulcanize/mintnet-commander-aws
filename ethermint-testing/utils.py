import os

import boto3
import logging

import time

from settings import DEFAULT_FILES_LOCATION, MAX_MACHINE_CALL_TRIES

logger = logging.getLogger(__name__)


def get_shh_key_file(filename):
    """
    A helper funtion which allows to find an SSH key file using the filename
    :param filename:
    :return: a full path of the key
    """
    if not filename.endswith(".pem"):
        filename += ".pem"

    full_filepath = os.path.join(DEFAULT_FILES_LOCATION, filename)
    if not os.path.exists(full_filepath):
        raise Exception("Key file {} missing".format(full_filepath))
    return full_filepath


def to_canonical_region_name(region):
    """
    In AWS, region names can be either us-west-1 or us-west-1b; when using an Availability zone,
    we want the more detailed version, but when playing with general ec2 interface, it needs to be the general name
    The availability zone consists of a region name with an additional letter in the end
    :param region:
    :return:
    """
    if region[-1].isalpha():
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


def run_sh_script(script_filename, ssh_key_name, ip_address):
    """
    Allows to run a shell script on an instance through SSH
    :param script_filename: the name of the script to be run
    :param ssh_key_name: the name of the ssh key to be used for the connection
    :param ip_address: the public IP address of the instance
    :return:
    """
    logger.info("Running ./{} on instance IP: {}".format(script_filename, ip_address))
    ssh_command = lambda ssh_key_file, ip, script: \
        "ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} 'bash -s' < {2}".format(ssh_key_file, ip, script)

    result = 1
    tries = 0
    while result != 0 and tries < MAX_MACHINE_CALL_TRIES:
        result = os.system(ssh_command(get_shh_key_file(ssh_key_name), ip_address, script_filename))
        tries += 1
        if result != 0:
            time.sleep(5)  # let things settle, SSH refuses connection
    if tries == MAX_MACHINE_CALL_TRIES:
        logger.error("Unable to perform actions using SSH")
    else:
        logger.info("{} run successfully".format(script_filename))
