import logging
import os
import subprocess
import time
from datetime import datetime, timedelta
from uuid import uuid4

import boto3
import dateutil
import pytz
from pathos.multiprocessing import ProcessingPool

from amibuilder import AMIBuilder
from chain import RegionInstancePair, Chain
from fill_validators import fill_validators, prepare_validators
from instance_creator import InstanceCreator
from settings import DEFAULT_INSTANCE_NAME, \
    DEFAULT_SECURITY_GROUP_DESCRIPTION, DEFAULT_PORTS, \
    DEFAULT_FILES_LOCATION, DEFAULT_LIVENESS_THRESHOLD
from utils import create_keyfile, run_sh_script, get_shh_key_file, run_ethermint

NETWORK_FAULT_PREPARATION_TIME_PER_INSTANCE = 10

logger = logging.getLogger(__name__)

TESTING = False


class Chainmanager:
    def __init__(self, num_processes=None):
        self.instance_creator = InstanceCreator(num_processes)

    def _create_security_group(self, name, ports, region):
        """
        Creates a security group in AWS based on ports
        :param name: the name of the newly created group
        :param ports: a list of tuples (ports as ints, protocol (tcp/udp))
        :param region: the AWS region
        :return: the SecurityGroup object
        """
        ec2 = boto3.resource('ec2', region_name=region)
        security_group = ec2.create_security_group(GroupName=name,
                                                   Description=DEFAULT_SECURITY_GROUP_DESCRIPTION)
        logger.info("Security group {} created".format(name))
        for (port, protocol) in ports:
            security_group.authorize_ingress(IpPermissions=[
                {
                    'IpProtocol': protocol,
                    'FromPort': port,
                    'ToPort': port,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                },
            ])
            logger.info("Added port {} to group {}".format(port, name))

        return security_group

    def get_roster(self, chains):
        """
        Generates a Salt-ssh roster from multiple chains
        :param chains: a list of Chain objects
        :return: a dictionary
        """
        master_roster = {}
        for chain_idx, chain in enumerate(chains):
            for region_pair in chain.instances:
                instance_data = dict(host=str(region_pair.public_ip_address),  # TODO private IP here
                                     user="ubuntu",
                                     sudo=True)
                instance_name = "chain{}_{}_{}".format(chain_idx, region_pair.region_name, region_pair.id)
                master_roster[instance_name] = instance_data

        return master_roster

    @staticmethod
    def _prepare_ethermint(chain):
        ethermint_files_location = os.path.join(DEFAULT_FILES_LOCATION, "ethermint")
        ethermint_genesis = os.path.join(ethermint_files_location, "data", "genesis.json")
        prepare_validators(len(chain.instances), ethermint_files_location)
        fill_validators(len(chain.instances), ethermint_genesis, ethermint_genesis, ethermint_files_location)

        for i, instance in enumerate(chain.instances):
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
    def _fix_ethermint_version(ethermint_version):
        if ethermint_version == "local":
            try:
                output = subprocess.check_output("git -C $GOPATH/src/github.com/tendermint/ethermint rev-parse HEAD",
                                                 shell=True)
                return output.strip()
            except subprocess.CalledProcessError as e:
                raise IOError("you have chosen \"local\" as your ethermint version, but getting commit"
                              "hash failed: {}".format(e.message))
        else:
            return ethermint_version

    def create_ethermint_network(self, regions, ethermint_version,
                                 name_root="test", no_ami_cache=False):
        """
        Creates an ethermint network in aws regions
        :param regions: A list of regions; one instance is created per region
        :param ethermint_version: hash (as str) or "local"
        :param name_root: Root of the names of amis to create
        :param no_ami_cache: Force rebuilding of Ethermint AMIs
        :return: a Chain object
        """
        for check in ["tendermint version", "ethermint -h", "packer version"]:
            if not os.system(check) == 0:
                raise EnvironmentError("{} not found in path".format(check))

        ethermint_version = self._fix_ethermint_version(ethermint_version)

        distinct_regions = set(regions)

        # Find AMI ID for each region and create AMIs if missing
        amis = {}
        ami_builder = AMIBuilder(packer_file_name="packer-file-ethermint-salt-ssh")
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
                full_name = "{}_ethermint{}_ami-ssh".format(name_root, ethermint_version[:8])
                ami_id = ami_builder.create_ami(ethermint_version, full_name,
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
        chain = Chain(map(RegionInstancePair.from_boto, nodes))

        logger.info("All minion {} instances running".format(len(regions)))

        self._prepare_ethermint(chain)
        run_ethermint(chain)

        for node in nodes:
            logger.info("Checking ethermint version {} on {}".format(ethermint_version,
                                                                     node.id))
            real_version = run_sh_script("shell_scripts/get_ethermint_version.sh",
                                         node.key_name,
                                         node.public_ip_address)
            real_version = real_version.strip()
            if real_version != ethermint_version:
                raise RuntimeError("Instance {} appears to be running ethermint {} instead of {}".format(
                    node.id, real_version, ethermint_version
                ))

        for node in nodes:
            logger.info("Ethermint instance ID: {} in {}".format(node.id, node.placement["AvailabilityZone"]))

        return chain

    @staticmethod
    def isalive(chain):
        """
        Checks if the consensus on the chain is making progress; for more details, use status
        :param chain: Chain object
        :return: bool
        """
        return Chainmanager.get_status(chain)['is_alive']

    @staticmethod
    def _is_alive(block, now):
        return abs((now - block.time).total_seconds()) <= DEFAULT_LIVENESS_THRESHOLD.total_seconds()

    @staticmethod
    def get_status(chain):
        """
        Checks the status of all of the nodes that form the chain
        :param chain: Chain object
        :return: dict
        """
        result = {'nodes': []}
        now = datetime.now(tz=pytz.UTC)

        for region_instance_pair in chain.instances:
            last_block = chain.chain_interface.get_latest_block(region_instance_pair.instance)
            result['nodes'].append({
                'instance_id': region_instance_pair.id,
                'instance_region': region_instance_pair.region_name,
                'name': region_instance_pair.instance_name,
                'height': last_block.height,
                'last_block_time': last_block.time.isoformat(),
                'last_block_height': last_block.height,
                'is_alive': Chainmanager._is_alive(last_block, now)
            })
        result['is_alive'] = all(node['is_alive'] for node in result['nodes'])
        heights = map(lambda node: node['height'], result['nodes'])
        result['height'] = reduce(lambda x, y: x + y, heights) / len(heights)
        result['age'] = None  # TODO: the total time that the chain has been running
        return result

    @staticmethod
    def get_history(chain, fromm=None, to=None):
        # FIXME: just pick a single instance to check history
        # FIXME: avoid digging into chain's internals? are these internals?
        # FIXME: rethink avoiding off-by-one errors with fromm/to according to some convention.
        #        Currently: returns to - from deltas, so to is inclusive, a'la tendermint RPC
        instance = chain.instances[0].instance

        interface = chain.chain_interface
        if to is None:
            to = interface.get_latest_block(instance).height
        if fromm is None:
            fromm = to - 1
        if fromm + 1 > to:
            raise ValueError("need at least 1 block between from and two to get block times")

        result = []

        blocks = list(reversed(interface.get_blocks(instance, fromm, to)))

        time = dateutil.parser.parse(blocks[0].time)
        for block in blocks[1:]:
            newtime = dateutil.parser.parse(block.time)
            delta = (newtime - time).total_seconds()
            result.append((delta, newtime.isoformat(), block.height))
            time = newtime

        return result

    @staticmethod
    def get_network_fault(chain, num_steps, delay_step, interval):
        # FIXME: using zeroth instance height & time as reference, consider checking instances' synchronisation?
        start_block = Chainmanager.get_status(chain)['nodes'][0]['height']

        # NOTE: "synchronized" is assumed here, should be in sync if NTP is running out there...
        remote_synchronized_time = run_sh_script('shell_scripts/get_datetime.sh',
                                                 chain.instances[0].key_name,
                                                 chain.instances[0].public_ip_address)

        time_to_prepare = timedelta(seconds=NETWORK_FAULT_PREPARATION_TIME_PER_INSTANCE * len(chain.instances))

        delay_start_time = dateutil.parser.parse(remote_synchronized_time) + time_to_prepare

        delaying_command = 'shell_scripts/run_tcs.sh {} {} {} {} {}'.format(
            num_steps,
            delay_step,
            interval,
            'eth0',
            delay_start_time.isoformat()
        )

        if not TESTING:
            # NOTE: only this branch actually does the job, delaying_command must be run in parallel
            pool = ProcessingPool(len(chain.instances))
            delay_step_times = pool.map((lambda instance:
                                         run_sh_script(delaying_command,
                                                       instance.key_name,
                                                       instance.public_ip_address)), chain.instances)
            pool.close()
            pool.join()
        else:
            # this is only in case where we're mocking and we cannot use multiprocessing of any form
            delay_step_times = []
            for instance in chain.instances:
                step_time = run_sh_script(delaying_command,
                                          instance.key_name,
                                          instance.public_ip_address)
                delay_step_times.append(step_time)

        # delay_step_times is a by-instance array of strings of by-step delays
        # grab zeroth instance results for now
        # FIXME: check consistence of per instance results?
        single_delay_step_times = delay_step_times[0].split('\n')

        delays = [delay_step * step for step in xrange(1, num_steps + 1)]
        # this zero relates to the last remote time measurement - final deleting of the netem delay
        delays.append(0)

        return dict(blocktimes=Chainmanager.get_history(chain, fromm=start_block),
                    delay_steps=zip(delays, single_delay_step_times))
