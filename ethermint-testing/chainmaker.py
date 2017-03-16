import logging
import os
import time
from datetime import datetime
from uuid import uuid4

import boto3

from amibuilder import AMIBuilder
from fill_validators import fill_validators, prepare_validators
from instance_creator import InstanceCreator
from settings import DEFAULT_INSTANCE_NAME, \
    DEFAULT_SECURITY_GROUP_DESCRIPTION, DEFAULT_PORTS, \
    DEFAULT_FILES_LOCATION
from utils import get_region_name, create_keyfile, run_sh_script, get_shh_key_file, run_ethermint

logger = logging.getLogger(__name__)


class Chainmaker:
    def __init__(self, num_processes=None):
        self.instance_creator = InstanceCreator(num_processes)

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

    def create_ethermint_network(self, regions, ethermint_version, master_pub_key, update_salt_roster=False,
                                 name_root="test", no_ami_cache=False):
        """
        Creates an ethermint network consisting of multiple ethermint nodes
        :param master_pub_key: master public key to be added to authorized keys
        :param ethermint_version: the hash of the ethermint commit
        :param name_root: the base of the AMI name
        :param regions: a list of regions where instances will be run; we run 1 instance per region
        :param update_salt_roster: indicates if the system /etc/salt/roster file should be updated
        :return: a list of all other instances created
        """
        for check in ["tendermint version", "ethermint -h", "packer version"]:
            if not os.system(check) == 0:
                raise EnvironmentError("{} not found in path".format(check))

        distinct_regions = set(regions)

        # Find AMI ID for each region and create AMIs if missing
        amis = {}
        ami_builder = AMIBuilder(master_pub_key, packer_file_name="packer-file-ethermint-salt-ssh")
        for region in distinct_regions:
            ec2 = boto3.resource('ec2', region_name=region)
            images = list(ec2.images.filter(Owners=['self'], Filters=[{'Name': 'tag:Ethermint',
                                                                       'Values': [ethermint_version]}]))
            if len(images) > 0 and no_ami_cache:
                for image in images:
                    logger.info("Deregistering AMI for {} in region {}".format(ethermint_version, region))
                    image.deregister()
                images = []

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
        create_keyfile(ethermint_network_keyfile, distinct_regions)

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

        nodes = self.instance_creator.create_ec2s_from_json(instances_config)
        logger.info("All minion {} instances running".format(len(regions)))

        if update_salt_roster:
            self._update_salt(nodes)
        self._prepare_ethermint(nodes)
        run_ethermint(nodes)

        for node in nodes:
            logger.info("Ethermint instance ID: {} in {}".format(node.id, node.placement["AvailabilityZone"]))

        return map(RegionInstancePair.from_boto, nodes)

    def isalive(self, region_instance):
        logger.info("Getting log on instance ID: {}".format(region_instance.id))

        output1 = run_sh_script("shell_scripts/log_ethermint.sh",
                                region_instance.instance.key_name,
                                region_instance.instance.public_ip_address)

        import time
        time.sleep(2)

        output2 = run_sh_script("shell_scripts/log_ethermint.sh",
                                region_instance.instance.key_name,
                                region_instance.instance.public_ip_address)

        return output1 != output2


class RegionInstancePair:
    """
    Region and ec2-resource bound instance. Picklable, workable as a boto3 Instance instance

    Main reason for this class is being picklable, which in turn is needed by our current parallel processing
    """
    def __init__(self, region_name, instance_id):
        self.region_name = region_name
        self.id = instance_id
        self.key_name = self.instance.key_name
        self.public_ip_address = self.instance.public_ip_address
        self.block_device_mappings = self.instance.block_device_mappings
        self.image_id = self.instance.image_id
        self.security_groups = self.instance.security_groups
        self.tags = self.instance.tags
        self.volumes = self.instance.volumes

    @staticmethod
    def from_boto(instance):
        return RegionInstancePair(get_region_name(instance.placement["AvailabilityZone"]), instance.id)

    @property
    def instance(self):
        """
        use instance.instance to instantiate the instance instance for instance id
        :return:
        """
        return self.ec2.Instance(self.id)

    @property
    def ec2(self):
        return boto3.resource('ec2', region_name=self.region_name)