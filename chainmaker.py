import logging
import os
import time

import boto3

from settings import DEFAULT_REGION, DEFAULT_INSTANCE_TYPE, DEFAULT_INSTANCE_NAME, \
    DEFAULT_SECURITY_GROUP_DESCRIPTION, DEFAULT_SNAPSHOT_VOLUME_SIZE, DEFAULT_DEVICE, DEFAULT_FILES_LOCATION
from utils import get_shh_key_file

logger = logging.getLogger(__name__)


class Chainmaker:
    def __init__(self):
        self.ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
        self.ec2_client = boto3.client('ec2', region_name=DEFAULT_REGION)

    def create_security_group(self, name, ports):
        """
        Creates a security group in AWS based on ports
        :param name: the name of the newly created group
        :param ports: a list of ports as ints
        :return: -
        """
        # TODO allow more complex ports definition
        security_group = self.ec2.create_security_group(GroupName=name,
                                                        Description=DEFAULT_SECURITY_GROUP_DESCRIPTION)
        logger.info("Security group {} created".format(name))
        for port in ports:
            security_group.authorize_ingress(IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': port,
                    'ToPort': port,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                },
            ])
            logger.info("Added port {} to group {}".format(port, name))

    @staticmethod
    def add_volume(instance):
        """
        Allows to create a new volume and attach it to an instance and mount it
        :param instance: the instance object
        :return: -
        """
        region = instance.placement["AvailabilityZone"]
        zone = region
        if region.endswith('a') or region.endswith('b'):
            zone = region[:-1]
        ec2 = boto3.resource('ec2', region_name=zone)

        volume = ec2.create_volume(Size=DEFAULT_SNAPSHOT_VOLUME_SIZE,
                                   AvailabilityZone=region)
        volume = ec2.Volume(volume.id)

        assert volume.availability_zone == instance.placement.get("AvailabilityZone")

        time.sleep(3)  # let things settle, volume does not exist yet :(

        if volume.state != 'available':
            ec2_client = boto3.client('ec2', region_name=zone)
            volume_waiter = ec2_client.get_waiter('volume_available')
            volume_waiter.wait(VolumeIds=[volume.id])

        volume.attach_to_instance(InstanceId=instance.id, Device=DEFAULT_DEVICE)
        logger.info("Attached volume {} to instance {}".format(volume.id, instance.id))

        logger.info("Running ./mount_new_volume.sh on instance {}".format(instance.id))
        mount_snapshot_command = lambda ssh_key, ip: \
            "ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} 'bash -s' < mount_new_volume.sh".format(ssh_key, ip)
        os.system(mount_snapshot_command(get_shh_key_file(instance.key_name),
                                         instance.public_ip_address))
        logger.info("New volume mounted successfully")

    def create(self, ami, number, security_group_name):
        """

        :param ami:
        :param number:
        :param security_group_name:
        :return:
        """
        instances = []

        for i in range(number):
            timestamp = "salt-instance" + str(int(time.time()))
            keyfile = timestamp + ".pem"

            key = self.ec2.create_key_pair(KeyName=timestamp)
            full_keyfile = os.path.join(DEFAULT_FILES_LOCATION, keyfile)
            with open(full_keyfile, 'w') as f:
                f.write(key.key_material)
            os.chmod(full_keyfile, 0o600)

            instance_config = {
                "region": DEFAULT_REGION,
                "ami": ami,
                "tags": [
                    {
                        "Key": "Name",
                        "Value": DEFAULT_INSTANCE_NAME + ami + str(i)
                    }
                ],
                "security_groups": [security_group_name],
                "key_name": timestamp,
                "add_volume": True
            }
            instances.append(Chainmaker.from_json(instance_config))

        logger.info("All {} instances running".format(number))
        return instances

    @staticmethod
    def from_json(config):
        """
        Runs an Ec2 instance based on it's config and returns the instance object
        :param config: the config HAS TO contain the following fields:
        "region", "ami", "tags", "security_groups", "key_name"
        the config MAY containg also:
        "add_volume"
        :return: instance object
        """
        ec2 = boto3.resource('ec2', region_name=config["region"])

        # create instances returns a list of instances, we want the first element
        instance = ec2.create_instances(ImageId=config["ami"],
                                        InstanceType=DEFAULT_INSTANCE_TYPE,
                                        MinCount=1,
                                        MaxCount=1,
                                        SecurityGroupIds=config["security_groups"],
                                        KeyName=config["key_name"])[0]
        instance.create_tags(Tags=config["tags"])
        instance.wait_until_running()

        if "add_volume" in config and config["add_volume"]:
            Chainmaker.add_volume(instance)

        logger.info("Created instance with ID {}".format(instance.id))

        return instance
