import multiprocessing

import boto3
import logging

from settings import DEFAULT_INSTANCE_TYPE, DEFAULT_SNAPSHOT_VOLUME_SIZE, DEFAULT_DEVICE
from utils import get_region_name, run_sh_script
from waiting_for_ec2 import wait_for_available_volume

logger = logging.getLogger(__name__)


class InstanceCreator:
    """
    Internal class which handles spinning up of ec2 instances according to configuration
    """
    def __init__(self, num_processes):
        self.num_processes = num_processes

    def create_ec2s_from_json(self, config):
        """
        Runs Ec2 instances based on config and returns the list of instance objects
        :param config: config consists of a list of instance configs
        each instance config HAS TO contain the following fields:
        "region", "ami", "security_groups", "key_name", "tags"
        the config MAY contain also:
        "add_volume", "tags" (additional tags)
        :return: a list of instance objects
        """

        if self.num_processes is None or self.num_processes == 1:
            instances_ids = []
            for conf in config:
                instances_ids.append(_create_instance(conf))
        else:
            # run in parallel, but this fails tests (because of moto), hence is based on an option
            # tried multiprocessing.ThreadPool which is ok with moto but has random errors
            # so, the default for tests is the sequential version above
            pool = multiprocessing.Pool(len(config))
            instances_ids = pool.map_async(_create_instance, config).get(600)
            pool.close()
            pool.join()

        ec2s = [boto3.resource('ec2', region_name=instance_config["region"]) for
                instance_config in config]

        instances = [ec2.Instance(instace_id) for ec2, instace_id in zip(ec2s, instances_ids)]
        return instances


def _create_instance(instance_config):
    """
    Helper - outside Chainmaker due to pickling for multiprocessing
    :param instance_config:
    :return: created instance's id
    """
    ec2 = boto3.resource('ec2', region_name=get_region_name(instance_config["region"]))
    # create instances returns a list of instances, we want the first element
    instance = ec2.create_instances(ImageId=instance_config["ami"],
                                    InstanceType=DEFAULT_INSTANCE_TYPE,
                                    MinCount=1,
                                    MaxCount=1,
                                    SecurityGroupIds=instance_config["security_groups"],
                                    KeyName=instance_config["key_name"])[0]
    instance.wait_until_running()
    instance.reload()
    if "add_volume" in instance_config and instance_config["add_volume"]:
        _add_volume(instance)
    if "tags" in instance_config and instance_config["tags"]:
        instance.create_tags(Tags=instance_config["tags"])
    logger.info("Created instance with ID {}".format(instance.id))
    return instance.id


def _add_volume(instance):
    """
    Outside Chainmaker due to pickling for multiprocessing
    Allows to create a new volume and attach it to an instance and mount it
    The volume is created in the same zone as the instnace
    :param instance: the instance object
    :return: -
    """
    region = get_region_name(instance.placement.get("AvailabilityZone"))
    ec2 = boto3.resource('ec2', region_name=region)

    volume = ec2.create_volume(Size=DEFAULT_SNAPSHOT_VOLUME_SIZE,
                               AvailabilityZone=instance.placement.get("AvailabilityZone"))
    volume = ec2.Volume(volume.id)
    volume.create_tags(Tags=[{'Key': 'Name', 'Value': 'ethermint_volume'}])

    assert volume.availability_zone == instance.placement.get("AvailabilityZone")

    wait_for_available_volume(volume, get_region_name(instance.placement["AvailabilityZone"]))

    instance.attach_volume(VolumeId=volume.id, Device=DEFAULT_DEVICE)
    logger.info("Attached volume {} to instance {}".format(volume.id, instance.id))

    run_sh_script("shell_scripts/mount_new_volume.sh", instance.key_name, instance.public_ip_address)