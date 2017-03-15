import os
import subprocess

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


def get_region_name(region):
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


def create_keyfile(name, regions_set):
    """
    Creates a key pair in AWS and saves the .pem file to default location,
    so that the user can connect to the instance using SSH
    :param name: the key name
    :param region: the region where the key should be created
    :return: the full key path
    """
    regions = list(regions_set)
    region = regions[0]
    ec2 = boto3.resource('ec2', region_name=region)
    keyfile = name + ".pem"
    key = ec2.create_key_pair(KeyName=name)
    full_keyfile = os.path.join(DEFAULT_FILES_LOCATION, keyfile)
    if not os.path.exists(DEFAULT_FILES_LOCATION):
        os.makedirs(DEFAULT_FILES_LOCATION)
    with open(full_keyfile, 'w+') as f:
        f.write(key.key_material)
    os.chmod(full_keyfile, 0o600)

    if len(regions) == 1:
        return full_keyfile  # done, no need to import in differen regions

    # there must be an easier way to do this as required by aws, but cannot find it :(,
    # tried OpenSSL, searched boto3 docs. It gets worse as moto returns the "key" result malformed
    openssh_public_material = subprocess.check_output(['ssh-keygen', '-y', '-f', full_keyfile])

    for other_region in regions[1:]:
        ec2 = boto3.resource('ec2', region_name=other_region)

        res = ec2.import_key_pair(KeyName=name,
                                  PublicKeyMaterial=openssh_public_material)
        print res.key_fingerprint


def run_sh_script(script_filename, ssh_key_name, ip_address):
    """
    Allows to run a shell script on an instance through SSH
    :param script_filename: the name of the script to be run
    :param ssh_key_name: the name of the ssh key to be used for the connection
    :param ip_address: the public IP address of the instance
    :return:
    """
    logger.info("Running ./{} on instance IP: {}".format(script_filename, ip_address))
    ssh_command = "ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} 'bash -s' < {2}" \
                  "".format(get_shh_key_file(ssh_key_name), ip_address, script_filename)

    result = 1
    tries = 0
    while result != 0 and tries < MAX_MACHINE_CALL_TRIES:
        try:
            tries += 1
            output = subprocess.check_output(ssh_command, shell=True)  # FIXME, shell=True unsafe
            result = 0
        except subprocess.CalledProcessError as e:
            logger.info("SSH {} to {}, No success yet, tries {}/{}: {}".format(script_filename,
                                                                               ip_address,
                                                                               tries,
                                                                               MAX_MACHINE_CALL_TRIES,
                                                                               e.message))
            time.sleep(5)  # let things settle, SSH refuses connection

    if tries == MAX_MACHINE_CALL_TRIES:
        raise IOError("Unable to perform actions using SSH, {} on {}".format(script_filename,
                                                                             ip_address))
    else:
        logger.info("{} run successfully".format(script_filename))
        return output


def run_ethermint(minion_instances):
    first_seed = None
    for i, instance in enumerate(minion_instances):
        logger.info("Running ethermint on instance ID: {}".format(instance.id))

        # run ethermint
        if first_seed is None:
            run_sh_script("shell_scripts/run_ethermint.sh",
                          instance.key_name,
                          instance.public_ip_address)
            first_seed = str(instance.public_ip_address) + ":46656"
        else:
            run_sh_script("shell_scripts/run_ethermint.sh {}".format(first_seed),
                          instance.key_name,
                          instance.public_ip_address)


def halt_ethermint(minion_instances):
    for i, instance in enumerate(minion_instances):
        logger.info("Halting ethermint on instance ID: {}".format(instance.id))

        run_sh_script("shell_scripts/halt_ethermint.sh",
                      instance.key_name,
                      instance.public_ip_address)