import logging
import os
import time

import boto3

from amibuilder import AMIBuilder
from settings import DEFAULT_REGION, DEFAULT_INSTANCE_TYPE, DEFAULT_INSTANCE_NAME, \
    DEFAULT_SECURITY_GROUP_DESCRIPTION, DEFAULT_SNAPSHOT_VOLUME_SIZE, DEFAULT_DEVICE, DEFAULT_PORTS
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

    @staticmethod
    def from_json(config):
        """
        Runs Ec2 instances based on config and returns the list of instance objects
        :param config: the config HAS TO contain the following fields (common for all instances):
        "region", "ami", "security_groups", "key_name", "tags"
        the config MAY containg also (individual), under i-th key:
        "add_volume", "tags" (additional tags)
        :return: a list of instance objects
        """
        ec2 = boto3.resource('ec2', region_name=to_canonical_region_name(config["region"]))

        # create instances returns a list of instances, we want the first element
        instances = ec2.create_instances(ImageId=config["ami"],
                                         InstanceType=DEFAULT_INSTANCE_TYPE,
                                         MinCount=1,
                                         MaxCount=1,
                                         SecurityGroupIds=config["security_groups"],
                                         KeyName=config["key_name"])
        for i, instance in enumerate(instances):
            if i in config:
                instance.create_tags(Tags=config[i]["tags"])
                instance.wait_until_running()
                if "add_volume" in config[i] and config[i]["add_volume"]:
                    Chainmaker.add_volume(instance)
            if "tags" in config and config["tags"]:
                instance.create_tags(Tags=config["tags"])

            logger.info("Created instance with ID {}".format(instance.id))

        return instances

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

        region = DEFAULT_REGION

        master_keyfile = "salt-instance-master" + str(int(time.time()))
        create_keyfile(master_keyfile, region)
        logger.info("Master SSH key in {}".format(master_keyfile))

        master_instance_config = {
            "region": region,
            "ami": master_ami,
            "security_groups": [security_group_id],
            "key_name": master_keyfile,
            0: {
                "tags": [
                    {
                        "Key": "Name",
                        "Value": DEFAULT_INSTANCE_NAME + master_ami
                    }
                ],
                "add_volume": True
            }
        }
        master_instance = Chainmaker.from_json(master_instance_config)[0]
        logger.info("Master instance running")

        # NOTE do we need separate SSH keys for each ethermint instance?
        minion_keyfile = "salt-instance-minion" + str(int(time.time()))
        create_keyfile(minion_keyfile, region)
        logger.info("Minion SSH key in {}".format(minion_keyfile))

        minion_instance_config = {
            "region": region,
            "ami": ethermint_node_ami,
            "security_groups": [security_group_id],
            "key_name": master_keyfile,
        }
        for i in range(ethermint_nodes_count):
            minion_instance_config[i] = {
                "tags": [
                    {
                        "Key": "Name",
                        "Value": DEFAULT_INSTANCE_NAME + ethermint_node_ami + str(i)
                    }
                ],
                "add_volume": True}

        minion_instances = Chainmaker.from_json(minion_instance_config)
        logger.info("All minion {} instances running".format(ethermint_nodes_count))

        return master_instance, minion_instances
