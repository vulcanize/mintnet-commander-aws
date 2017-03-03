import json
import logging

import boto3
import click

from amibuilder import AMIBuilder
from chainmaker import Chainmaker
from chainshotter import Chainshotter
from settings import DEFAULT_REGION

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class CommandEnvironment(object):
    def __init__(self):
        self.chainshotter = Chainshotter()
        self.chainmaker = Chainmaker()

pass_environment = click.make_pass_decorator(CommandEnvironment, ensure=True)


@click.group()
def ethermint_testing():
    pass


@ethermint_testing.command()
@click.option('--count', default=1, help='Number of ethermints to be run')
@click.option('--master-ami', required=True, help='The AMI to be used for the master node')
@click.option('--ethermint-node-ami', required=True, help='The AMI to be used for ethermint nodes')
@pass_environment
def create(env, count, master_ami, ethermint_node_ami):
    """
    Creates an ethermint network consisting of 1 master node and some ethermint nodes
    """
    master, minions = env.chainmaker.create_ethermint_network(count, master_ami, ethermint_node_ami)
    logger.info("Master ID: {}".format(master.id))
    for minion in minions:
        logger.info("Ethermint instance ID: {}".format(minion.id))
    return master, minions


@ethermint_testing.command()
@click.option('--name', default="Ethermint-network-chainshot", help='The name of the chainshot')
@click.option('--instances', required=True, default=[], type=click.STRING, multiple=True, help='The list of ethermint instance objects')
@click.option('--output-file-path', default="chainshot.json", help='Output chainshot file path (json)')
@pass_environment
def chainshot(env, name, instances, output_file_path):
    """
    Allows to create a chainshot of a network consisting of multiple ec2 instances
    Instances should contain the master node
    """
    ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)  # FIXME different regions
    instance_objects = []
    for instance in instances:
        instance_objects.append(ec2.Instance(instance))
    chainshot_data = env.chainshotter.chainshot(name, instance_objects)
    with open(output_file_path, 'w') as f:
        json.dump(chainshot_data, f, indent=2)
    logger.info("The chainshot: {}".format(chainshot_data))


@ethermint_testing.command()
@click.argument('chainshot-file', type=click.Path(exists=True))
@pass_environment
def thaw(env, chainshot_file):
    """
    Allows to unfreeze a network from a config
    """
    with open(chainshot_file) as json_data:
        chainshot = json.load(json_data)
        instances = env.chainshotter.thaw(chainshot)
        for instance in instances:
            logger.info("Instance ID: {} unfreezed from chainshot".format(instance.id))
        return instances


@ethermint_testing.command()
@pass_environment
def create_amis(env):
    """
    Builds and deploys EC2 AMIs for master and minions, returns master AMI ID and minion AMI ID
    """
    from packer_configs.salt_ssh_master_config import packer_salt_ssh_master_config
    from packer_configs.salt_ssh_minion_config import packer_salt_ssh_minion_config
    master_ami_builder = AMIBuilder(packer_file_name="packer-file-salt-ssh-master-test")
    minion_ami_builder = AMIBuilder(packer_file_name="packer-file-salt-ssh-minion-test")
    master_ami = master_ami_builder.create_ami(packer_salt_ssh_master_config, "test_salt_ssh_master_ami")
    minion_ami = minion_ami_builder.create_ami(packer_salt_ssh_minion_config, "test_salt_ssh_minion_ami")
    logger.info("Master AMI: {}".format(master_ami))
    logger.info("Ethermint node AMI: {}".format(minion_ami))
    return master_ami, minion_ami


cli = click.CommandCollection(sources=[ethermint_testing])

if __name__ == '__main__':
    cli()
