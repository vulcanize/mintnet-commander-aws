import json
import logging
import os

import click

from chain import Chain
from chainmanager import Chainmanager, RegionInstancePair
from chainshotter import Chainshotter
from settings import DEFAULT_FILES_LOCATION
from utils import print_nodes

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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
    chainmanager = Chainmanager(num_processes=num_processes)
    nodes = chainmanager.create_ethermint_network(regions, ethermint_version, master_pub_key, update_roster, name_root,
                                                no_ami_cache=no_ami_cache)

    print_nodes(nodes)


@ethermint_testing.command(help='Pass as arguments the list of ethermint instance objects, '
                                'supplied in "region:id" pairs')
@click.option('--name', default="Ethermint-network-chainshot", help='The name of the chainshot')
@click.option('--output-file-path', default="chainshot.json", help='Output chainshot file path (json)')
@click.argument('instances', type=unicode, nargs=-1)
def chainshot(name, instances, output_file_path):
    """
    Allows to create a chainshot of a network consisting of multiple ec2 instances
    """
    instances = [RegionInstancePair(*instance.split(':')) for instance in instances]
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


@ethermint_testing.command(help="check if the consensus on the chain is making progress; Pass pairs of region:id")
@click.argument('instances', type=unicode, nargs=-1)
def isalive(instances):
    chain = Chain([RegionInstancePair(*instance.split(':')) for instance in instances])
    print Chainmanager.isalive(chain)


@ethermint_testing.command(help="check the status of all of the nodes that form the chain; Pass pairs of region:id")
@click.argument('instances', type=unicode, nargs=-1)
def status(instances):
    chain = Chain([RegionInstancePair(*instance.split(':')) for instance in instances])
    print Chainmanager.get_status(chain)


# jesli to jest ethermint, to dodatkowo sprawdzamy z geth czy informacje sie zgadzaja i tylko wtedy jest isalive
# create, chainshot powinny zwracac identycznego jsona, ktorego potem mozna uzyc jako argumnet chain
# ten json powinien explicite zawierac informacje o tym, jaki to jest chain (ethermint)


# live chain json-example, json file which describes the meta data about a running chain
# to serve as input to the CLI app (as json file) it needs to support at least
# jayson['instances']['instance']['id']
# so a json file like the "chainshot" json without 'snapshot' fields works


# for later, for now just for reference
# def history(chain, fromm, to):
#     b = {
#         'nodes': [
#             {
#                 'name???': 'node1',
#                 'blocktimes': ['isotime1', 'isotime2...'],
#                 'txcounts': [0, 2]
#             }
#         ]
#     }


cli = click.CommandCollection(sources=[ethermint_testing])

if __name__ == '__main__':
    cli()
