import json
import logging
import os

import click

from chainmaker import Chainmaker, RegionInstancePair
from chainshotter import Chainshotter
from settings import DEFAULT_FILES_LOCATION
from utils import print_nodes

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# FIXME: not used anymore as our api instances depend on arguments, delete if it's not coming back
# class CommandEnvironment(object):
#     def __init__(self):
#         pass
#
#
# pass_environment = click.make_pass_decorator(CommandEnvironment, ensure=True)


@click.group()
def ethermint_testing():
    pass


@ethermint_testing.command()
@click.option('--update-roster/--no-update-roster', default=False, help='Update /etc/salt/roster locally?')
@click.option('--regions', '-r', required=True, default=None, type=click.STRING, multiple=True,
              help='A list of regions; one instance is created per region')
@click.option('--ethermint-version', default="local", help='The hash of ethermints commit or local to use '
                                                           'local version in GOPATH (default)')
@click.option('--master-pkey-name', required=True, help='')
@click.option('--name-root', default="test", help='Root of the names of amis to create')
@click.option('--num-processes', '-n', default=None, type=click.INT,
              help='specify >1 if you want to run instance creation in parallel using multiprocessing')
@click.option('--no-ami-cache', is_flag=True, help='Force rebuilding of Ethermint AMIs')
def create(update_roster, regions, ethermint_version, master_pkey_name, name_root, num_processes, no_ami_cache):
    """
    Creates an ethermint network consisting of ethermint nodes
    """
    with open(os.path.join(DEFAULT_FILES_LOCATION, master_pkey_name + '.key.pub'), 'r') as f:
        master_pub_key = f.read()
    chainmaker = Chainmaker(num_processes=num_processes)
    nodes = chainmaker.create_ethermint_network(regions, ethermint_version, master_pub_key, update_roster, name_root,
                                                no_ami_cache=no_ami_cache)

    print_nodes(nodes)


@ethermint_testing.command()
@click.option('--name', default="Ethermint-network-chainshot", help='The name of the chainshot')
@click.option('--instances', '-i', required=True, default=[], type=(unicode, unicode),
              multiple=True, help='The list of ethermint instance objects, supplied in "region id" paris')
@click.option('--output-file-path', default="chainshot.json", help='Output chainshot file path (json)')
def chainshot(name, instances, output_file_path):
    """
    Allows to create a chainshot of a network consisting of multiple ec2 instances
    """
    instances = [RegionInstancePair(*instance) for instance in instances]
    chainshot_data = Chainshotter().chainshot(name, instances)
    with open(output_file_path, 'w') as f:
        json.dump(chainshot_data, f, indent=2)
    logger.info("The chainshot: {}".format(chainshot_data))


@ethermint_testing.command()
@click.argument('chainshot-file', type=click.Path(exists=True))
@click.option('--num-processes', '-n', default=None, type=click.INT,
              help='specify >1 if you want to run instance creation in parallel using multiprocessing')
def thaw(chainshot_file, num_processes):
    """
    Allows to unfreeze a network from a config
    """
    with open(chainshot_file) as json_data:
        chainshot = json.load(json_data)

    instances = Chainshotter(num_processes).thaw(chainshot)
    print_nodes(instances)


@ethermint_testing.command(help="quick ugly check if the consensus on the instance is making progress"
                                "usage: isalive region instance_id")
@click.argument('instance', type=(unicode, unicode))
def isalive(instance):
    print Chainmaker().isalive(RegionInstancePair(*instance))


cli = click.CommandCollection(sources=[ethermint_testing])

if __name__ == '__main__':
    cli()
