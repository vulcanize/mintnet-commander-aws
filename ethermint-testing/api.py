import json
import logging
import os

import click

from amibuilder import AMIBuilder
from chainmaker import Chainmaker
from chainshotter import Chainshotter, RegionInstancePair
from settings import DEFAULT_FILES_LOCATION

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class CommandEnvironment(object):
    def __init__(self):
        self.chainshotter = Chainshotter()


pass_environment = click.make_pass_decorator(CommandEnvironment, ensure=True)


@click.group()
def ethermint_testing():
    pass


@ethermint_testing.command()
@click.option('--update-roster/--no-update-roster', default=False, help='Update /etc/salt/roster locally?')
@click.option('--regions', '-r', required=True, default=None, type=click.STRING, multiple=True,
              help='A list of regions; one instance is created per region')
@click.option('--ethermint-version', default="HEAD", help='The hash of ethermints commit')
@click.option('--master-pkey-name', required=True, help='')
@click.option('--name-root', default="test", help='Root of the names of amis to create')
@click.option('--num-processes', '-n', default=None, type=click.INT,
              help='specify >1 if you want to run instance creation in parallel using multiprocessing')
@pass_environment
def create(env, update_roster, regions, ethermint_version, master_pkey_name, name_root, num_processes):
    """
    Creates an ethermint network consisting of ethermint nodes
    """
    with open(os.path.join(DEFAULT_FILES_LOCATION, master_pkey_name + '.key.pub'), 'r') as f:
        master_pub_key = f.read()
    chainmaker = Chainmaker(num_processes=num_processes)
    nodes = chainmaker.create_ethermint_network(regions, ethermint_version, master_pub_key, update_roster, name_root)

    _print_nodes(nodes)


@ethermint_testing.command()
@click.option('--name', default="Ethermint-network-chainshot", help='The name of the chainshot')
@click.option('--instances', '-i', required=True, default=[], type=(unicode, unicode),
              multiple=True, help='The list of ethermint instance objects, supplied in "region id" paris')
@click.option('--output-file-path', default="chainshot.json", help='Output chainshot file path (json)')
@pass_environment
def chainshot(env, name, instances, output_file_path):
    """
    Allows to create a chainshot of a network consisting of multiple ec2 instances
    """
    instances = [RegionInstancePair(*instance) for instance in instances]
    chainshot_data = env.chainshotter.chainshot(name, instances)
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
    _print_nodes(instances)


@ethermint_testing.command(help="quick ugly check if the consensus on the instance is making progress"
                                "usage: isalive region instance_id")
@click.argument('instance', type=(unicode, unicode))
def isalive(instance):
    print Chainmaker().isalive(RegionInstancePair(*instance))


def _print_nodes(nodes):
    """
    notify cli user using print
    :param nodes: boto3 instances
    """
    print "Ethermint instances:"
    for node in nodes:
        region = node.placement["AvailabilityZone"][:-1]  # region is more useful for further processing
        print "{} {}".format(region, node.id)
    print "Check ethermint alive (printing to console really...) with isalive <region> <instance id>"


cli = click.CommandCollection(sources=[ethermint_testing])

if __name__ == '__main__':
    cli()
