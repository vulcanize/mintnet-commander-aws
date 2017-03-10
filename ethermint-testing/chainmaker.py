import logging
import multiprocessing
import os
import time
from datetime import datetime
from uuid import uuid4

import boto3

from amibuilder import AMIBuilder
from fill_validators import fill_validators, prepare_validators
from settings import DEFAULT_INSTANCE_TYPE, DEFAULT_INSTANCE_NAME, \
    DEFAULT_SECURITY_GROUP_DESCRIPTION, DEFAULT_SNAPSHOT_VOLUME_SIZE, DEFAULT_DEVICE, DEFAULT_PORTS, \
    DEFAULT_FILES_LOCATION
from utils import get_region_name, create_keyfile, run_sh_script, get_shh_key_file
from waiting_for_ec2 import wait_for_available_volume

logger = logging.getLogger(__name__)


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


class Chainmaker:
    def __init__(self):
        pass

    def _create_security_group(self, name, ports, region):
        """
        Creates a security group in AWS based on ports
        :param name: the name of the newly created group
        :param ports: a list of ports as ints
        :param region: the AWS region
        :return: the SecurityGroup object
        """
        ec2 = boto3.resource('ec2', region_name=region)
        security_group = ec2.create_security_group(GroupName=name,
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
        # comment this to run in paralell (see below)
        instances_ids = []
        for conf in config:
            instances_ids.append(_create_instance(conf))

        # uncomment the following to run in parallel, but this fails tests (because of moto)
        # tried multiprocessing.ThreadPool which is ok with moto but has random errors
        # so, the default for tests is the sequential version above
        # pool = multiprocessing.Pool(len(config))
        # instances_ids = pool.map_async(_create_instance, config).get(600)
        # pool.close()
        # pool.join()

        ec2s = [boto3.resource('ec2', region_name=instance_config["region"]) for
                instance_config in config]

        instances = [ec2.Instance(instace_id) for ec2, instace_id in zip(ec2s, instances_ids)]
        return instances

    def _update_salt(self, instances):
        master_roster_file = ""
        for i, instance in enumerate(instances):
            master_roster_file += "node" + str(i) + ":\n"
            master_roster_file += "    host: " + str(instance.public_ip_address) + "\n"  # TODO private IP here
            master_roster_file += "    user: ubuntu\n"
            master_roster_file += "    sudo: True\n"

        roster_path = os.path.join(DEFAULT_FILES_LOCATION, "roster")
        with open(roster_path, 'w') as f:
            f.write(master_roster_file)

        os.system("shell_scripts/copy_roster.sh {}".format(roster_path))

    @staticmethod
    def _prepare_ethermint(minion_instances):
        ethermint_files_location = os.path.join(DEFAULT_FILES_LOCATION, "ethermint")
        ethermint_genesis = os.path.join(ethermint_files_location, "data", "genesis.json")
        prepare_validators(len(minion_instances), ethermint_files_location)
        fill_validators(len(minion_instances), ethermint_genesis, ethermint_genesis, ethermint_files_location)

        for i, instance in enumerate(minion_instances):
            logger.info("Preparing ethermint on instance ID: {}".format(instance.id))
            run_sh_script("shell_scripts/prepare_ethermint_env.sh", instance.key_name, instance.public_ip_address)

            # copy the pre-inited chain data
            # FIXME: better to init on the remote host using remote ethermint?
            # this could only upload the genesis.json
            os.system(
                "scp -o StrictHostKeyChecking=no -C -i {} -r {} ubuntu@{}:/ethermint".format(
                    get_shh_key_file(instance.key_name), os.path.join(ethermint_files_location, "data"),
                    instance.public_ip_address))

            # copy the validator file
            validator_filename = "priv_validator.json.{}".format(i + 1)
            src_validator_path = os.path.join(ethermint_files_location, validator_filename)
            os.system(
                "scp -o StrictHostKeyChecking=no -C -i {} {} ubuntu@{}:/ethermint/data/priv_validator.json".format(
                    get_shh_key_file(instance.key_name), src_validator_path, instance.public_ip_address))

    @staticmethod
    def _run_ethermint(minion_instances):
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

    def create_ethermint_network(self, regions, ethermint_version, master_pub_key, update_salt_roster=False,
                                 name_root="test"):
        """
        Creates an ethermint network consisting of multiple ethermint nodes
        :param master_pub_key: master public key to be added to authorized keys
        :param ethermint_version: the hash of the ethermint commit
        :param name_root: the base of the AMI name
        :param regions: a list of regions where instances will be run; we run 1 instance per region
        :param update_salt_roster: indicates if the system /etc/salt/roster file should be updated
        :return: a list of all other instances created
        """
        distinct_regions = set(regions)

        # Find AMI ID for each region and create AMIs if missing
        amis = {}
        ami_builder = AMIBuilder(master_pub_key, packer_file_name="packer-file-ethermint-salt-ssh")
        for region in distinct_regions:
            ec2 = boto3.resource('ec2', region_name=region)
            images = list(ec2.images.filter(Owners=['self'], Filters=[{'Name': 'tag:Ethermint',
                                                                       'Values': [ethermint_version]}]))
            if len(images) > 0:
                logger.info("AMI for {} in region {} already exists".format(ethermint_version, region))
                amis[region] = images[0].id
            else:
                logger.info("Creating AMI for {} in region {}".format(ethermint_version, region))
                ami_id = ami_builder.create_ami(ethermint_version, name_root + "_ethermint_ami-ssh",
                                                regions=[region])
                amis[region] = ami_id

        # Create security groups in all regions
        security_groups = {}
        security_group_name = "ethermint-security_group-salt-ssh-" + str(datetime.now())
        for region in distinct_regions:
            group = self._create_security_group(security_group_name, DEFAULT_PORTS, region)
            security_groups[region] = group.id

        instances_config = []

        # Create a common key in all regions
        ethermint_network_keyfile = "salt-instance-" + str(int(time.time())) + "_" + uuid4().hex
        for region in distinct_regions:
            create_keyfile(ethermint_network_keyfile, region)

        logger.info("Nodes SSH key in {}".format(ethermint_network_keyfile))

        for i, region in enumerate(regions):
            instances_config.append({
                "region": region,
                "ami": amis[region],
                "security_groups": [security_groups[region]],
                "key_name": ethermint_network_keyfile,
                "tags": [
                    {
                        "Key": "Name",
                        "Value": DEFAULT_INSTANCE_NAME + amis[region] + str(i)
                    }
                ],
                "add_volume": True
            })

        nodes = self.create_ec2s_from_json(instances_config)
        logger.info("All minion {} instances running".format(len(regions)))

        if update_salt_roster:
            self._update_salt(nodes)
        self._prepare_ethermint(nodes)
        self._run_ethermint(nodes)

        for node in nodes:
            logger.info("Ethermint instance ID: {} in {}".format(node.id, node.placement["AvailabilityZone"]))

        return nodes
