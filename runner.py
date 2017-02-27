import boto3
import time

from amibuilder import AMIBuilder
from chainmaker import Chainmaker
from chainshotter import Chainshotter
from packer_configs.salt_master_config import packer_salt_master_config
from packer_configs.salt_minion_config import packer_salt_minion_config

ami_builder = AMIBuilder()
chain_maker = Chainmaker()
chain_shotter = Chainshotter()

master_ami = ami_builder.create_ami(packer_salt_master_config, "test_salt_master_ami-2", "packer-file-salt-master")
master_instances = chain_maker.create(master_ami, 1)

ec2 = boto3.resource('ec2')
master_ip = ec2.Instance(master_instances[0].id).public_ip_address
minion_ami = ami_builder.create_ami(packer_salt_minion_config(master_ip), "test_salt_minion_ami-2", "packer-file-salt-minion")

minion_instances = chain_maker.create(minion_ami, 3)

# make sure everything is initialized properly
time.sleep(60)

chain_shotter.chainshot("my_first_test_snapshot", minion_instances)
