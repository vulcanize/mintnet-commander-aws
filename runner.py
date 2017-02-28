import boto3
import time

import logging

from amibuilder import AMIBuilder
from chainmaker import Chainmaker
from chainshotter import Chainshotter
from packer_configs.salt_master_config import packer_salt_master_config
from packer_configs.salt_minion_config import packer_salt_minion_config
from settings import DEFAULT_PORTS, DEFAULT_REGION


logging.basicConfig(level=logging.INFO)

ami_builder = AMIBuilder()
chain_maker = Chainmaker()
chain_shotter = Chainshotter()

security_group_name = "ethermint-security_group"
# chain_maker.create_security_group(security_group_name, DEFAULT_PORTS)

# master_ami = ami_builder.create_ami(packer_salt_master_config, "test_salt_master_ami-1", "packer-file-salt-master")
master_ami = "ami-ac63bcba"
master_instances = chain_maker.create(master_ami, 1, security_group_name)

ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
master_ip = ec2.Instance(master_instances[0].id).public_ip_address
minion_ami = ami_builder.create_ami(packer_salt_minion_config(master_ip), "test_salt_minion_ami-1", "packer-file-salt-minion")

minion_instances = chain_maker.create(minion_ami, 3, security_group_name)

# make sure everything is initialized properly
time.sleep(60)

chain_shotter.chainshot("my_first_test_snapshot", minion_instances)
