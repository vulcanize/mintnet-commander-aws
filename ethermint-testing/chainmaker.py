import logging
import time
from datetime import datetime

import boto3

from settings import DEFAULT_REGION, DEFAULT_INSTANCE_TYPE, DEFAULT_INSTANCE_NAME, \
    DEFAULT_SECURITY_GROUP_DESCRIPTION, DEFAULT_SNAPSHOT_VOLUME_SIZE, DEFAULT_DEVICE, DEFAULT_PORTS
from utils import to_canonical_region_name, create_keyfile, run_sh_script
from waiting_for_ec2 import wait_for_available_volume

logger = logging.getLogger(__name__)


class Chainmaker:
    def __init__(self):
        self.ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)  # FIXME different regions

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
        region = to_canonical_region_name(instance.placement.get("AvailabilityZone"))
        ec2 = boto3.resource('ec2', region_name=region)

        volume = ec2.create_volume(Size=DEFAULT_SNAPSHOT_VOLUME_SIZE,
                                   AvailabilityZone=instance.placement.get("AvailabilityZone"))
        volume = ec2.Volume(volume.id)
        volume.create_tags(Tags=[{'Key': 'Name', 'Value': 'ethermint_volume'}])

        assert volume.availability_zone == instance.placement.get("AvailabilityZone")

        wait_for_available_volume(volume, to_canonical_region_name(instance.placement["AvailabilityZone"]))

        instance.attach_volume(VolumeId=volume.id, Device=DEFAULT_DEVICE)
        logger.info("Attached volume {} to instance {}".format(volume.id, instance.id))

        run_sh_script("shell_scripts/mount_new_volume.sh", instance.key_name, instance.public_ip_address)

    @staticmethod
    def create_ec2s_from_json(config):
        """
        Runs Ec2 instances based on config and returns the list of instance objects
        :param config: config consists of a list of instance configs
        each instance config HAS TO contain the following fields:
        "region", "ami", "security_groups", "key_name", "tags"
        the config MAY contain also:
        "add_volume", "tags" (additional tags)
        :return: a list of instance objects
        """
        instances = []

        for i, instance_config in enumerate(config):
            ec2 = boto3.resource('ec2', region_name=to_canonical_region_name(instance_config["region"]))

            # create instances returns a list of instances, we want the first element
            instance = ec2.create_instances(ImageId=instance_config["ami"],
                                            InstanceType=DEFAULT_INSTANCE_TYPE,
                                            MinCount=1,
                                            MaxCount=1,
                                            SecurityGroupIds=instance_config["security_groups"],
                                            KeyName=instance_config["key_name"])[0]
            instances.append(instance)
            instance.wait_until_running()
            instance.reload()

            if "add_volume" in instance_config and instance_config["add_volume"]:
                Chainmaker.add_volume(instance)
            if "tags" in instance_config and instance_config["tags"]:
                instance.create_tags(Tags=instance_config["tags"])

            logger.info("Created instance with ID {}".format(instance.id))

        return instances

    def create_ethermint_network(self, ethermint_nodes_count, master_ami, ethermint_node_ami):
        """
        Creates an ethermint network consisting of multiple ethermint nodes and a single master node
        For now, all the nodes are in the same region
        :param ethermint_node_ami:  The AMI in the default region which will be used to build the ethermint nodes;
        :param master_ami: The AMI in the default region which will be used to build master node;
        :param ethermint_nodes_count: The number of ethermint nodes to be run (does not contain master node)
        :return: a master instance and a list of all other instances created
        """

        security_group_name = "ethermint-security_group-salt-ssh-" + str(datetime.now())
        group = self.create_security_group(security_group_name, DEFAULT_PORTS)
        security_group_id = group.id

        region = DEFAULT_REGION

        master_keyfile = "salt-instance-master" + str(int(time.time()))
        create_keyfile(master_keyfile, region)
        logger.info("Master SSH key in {}".format(master_keyfile))

        master_instance_config = [{
            "region": region,
            "ami": master_ami,
            "security_groups": [security_group_id],
            "key_name": master_keyfile,
            "tags": [
                {
                    "Key": "Name",
                    "Value": DEFAULT_INSTANCE_NAME + master_ami
                }
            ],
            "add_volume": False
        }]
        master_instance = Chainmaker.create_ec2s_from_json(master_instance_config)[0]
        logger.info("Master instance running")

        # NOTE do we need separate SSH keys for each ethermint instance? For now we have a common key for all
        minion_keyfile = "salt-instance-minion" + str(int(time.time()))
        create_keyfile(minion_keyfile, region)
        logger.info("Minion SSH key in {}".format(minion_keyfile))

        minion_instances_config = []

        for i in range(ethermint_nodes_count):
            minion_instances_config.append({
                "region": region,
                "ami": ethermint_node_ami,
                "security_groups": [security_group_id],
                "key_name": minion_keyfile,
                "tags": [
                    {
                        "Key": "Name",
                        "Value": DEFAULT_INSTANCE_NAME + ethermint_node_ami + str(i)
                    }
                ],
                "add_volume": True
            })

        minion_instances = Chainmaker.create_ec2s_from_json(minion_instances_config)
        logger.info("All minion {} instances running".format(ethermint_nodes_count))

        master_roster_file = ""
        for i, minion in enumerate(minion_instances):
            master_roster_file += "node" + str(i) + "\n"
            master_roster_file += "    host: " + str(minion.public_ip_address) + "\n"  # TODO should be private IP here
            master_roster_file += "    user: ubuntu\n"
            master_roster_file += "    sudo: True\n"

        run_sh_script("shell_scripts/fill_roster.sh '{}'".format(master_roster_file),
                      master_instance.key_name,
                      master_instance.public_ip_address)

        # # FIXME use salt for this?
        # # We should also generate genesis files and upload them here
        # first_seed = None
        # for i, instance in enumerate(minion_instances):
        #     logger.info("Running ethermint on instance ID: {}".format(instance.id))
        #     if first_seed is None:
        #         run_sh_script("shell_scripts/run_ethermint.sh {}".format(i),
        #                       instance.key_name,
        #                       instance.public_ip_address)
        #         first_seed = str(instance.public_ip_address) + ":46656"
        #     else:
        #         run_sh_script("shell_scripts/run_ethermint.sh {}".format(i, first_seed),
        #                       instance.key_name,
        #                       instance.public_ip_address)

        return master_instance, minion_instances
