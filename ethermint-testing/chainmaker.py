import logging
import os
import time

import boto3

from amibuilder import AMIBuilder
from settings import DEFAULT_REGION, DEFAULT_INSTANCE_TYPE, DEFAULT_INSTANCE_NAME, \
    DEFAULT_SECURITY_GROUP_DESCRIPTION, DEFAULT_SNAPSHOT_VOLUME_SIZE, DEFAULT_DEVICE, DEFAULT_FILES_LOCATION, \
    DEFAULT_PORTS
from utils import get_shh_key_file, to_canonical_region_name, create_keyfile

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
        :return: the SecurityGroup object
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

        return security_group

    @staticmethod
    def add_volume(instance):
        """
        Allows to create a new volume and attach it to an instance and mount it
        :param instance: the instance object
        :return: -
        """
        region = instance.placement["AvailabilityZone"]
        ec2 = boto3.resource('ec2', region_name=to_canonical_region_name(region))

        volume = ec2.create_volume(Size=DEFAULT_SNAPSHOT_VOLUME_SIZE,
                                   AvailabilityZone=region)
        volume = ec2.Volume(volume.id)
        volume.create_tags(Tags=[{'Key': 'Name', 'Value': 'ethermint_volume'}])

        assert volume.availability_zone == instance.placement.get("AvailabilityZone")

        # time.sleep(3)  # let things settle, volume does not exist yet :(

        if volume.state != 'available':
            ec2_client = boto3.client('ec2', region_name=to_canonical_region_name(region))
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

    def create(self, ami, number, security_group_id):
        """

        :param ami:
        :param number:
        :param security_group_id:
        :return:
        """
        instances = []

        for i in range(number):
            timestamp = "salt-instance" + str(int(time.time()))

            # TODO allow to define a custom region config and read the data from there
            region = DEFAULT_REGION

            create_keyfile(timestamp, region)

            instance_config = {
                "region": region,
                "ami": ami,
                "tags": [
                    {
                        "Key": "Name",
                        "Value": DEFAULT_INSTANCE_NAME + ami + str(i)
                    }
                ],
                "security_groups": [security_group_id],
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
        ec2 = boto3.resource('ec2', region_name=to_canonical_region_name(config["region"]))

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

    def create_ethermint_network(self, ethermint_nodes_count, master_ami=None, ethermint_node_ami=None,
                                 security_group_id=None):
        """
        Creates an ethermint network consisting of multiple ethermint nodes and a single master node
        For now, all the nodes are in the same region
        :param security_group_id: The name of the security group to be used; if not given, a default group will be created
        :param ethermint_node_ami:  The AMI in the default region which will be used to build the ethermint nodes;
        if not provided, default AMI will be deployed
        :param master_ami: The AMI in the default region which will be used to build master node;
        if not provided, default master AMI will be deployed
        :param ethermint_nodes_count: The number of ethermint nodes to be run (does not contain master node)
        :return: A list of all instances created (including master)
        """
        if master_ami is None:
            from packer_configs.salt_ssh_master_config import packer_salt_ssh_master_config
            master_ami_builder = AMIBuilder("packer-file-salt-ssh-master")
            master_ami = master_ami_builder.create_ami(packer_salt_ssh_master_config,
                                                       "test_salt_ssh_master_ami")
        if ethermint_node_ami is None:
            from packer_configs.salt_ssh_minion_config import packer_salt_ssh_minion_config
            minion_ami_builder = AMIBuilder("packer-file-salt-ssh-minion")
            ethermint_node_ami = minion_ami_builder.create_ami(packer_salt_ssh_minion_config,
                                                               "test_salt_ssh_minion_ami")

        if security_group_id is None:
            security_group_name = "ethermint-security_group-salt-ssh"
            group = self.create_security_group(security_group_name, DEFAULT_PORTS)
            security_group_id = group.id

        master_instance = self.create(master_ami, 1, security_group_id)[0]
        minion_instances = self.create(ethermint_node_ami, ethermint_nodes_count, security_group_id)
        all_instances = [master_instance] + minion_instances
        return all_instances
