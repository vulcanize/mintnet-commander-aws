import json
import logging
import os

import click
import yaml

from chain import Chain
from chainmanager import Chainmanager
from chainshotter import Chainshotter
from settings import DEFAULT_FILES_LOCATION

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@click.group()
def ethermint_testing():
    pass


@ethermint_testing.command()
@click.option('--regions', '-r', required=True, default=None, type=click.STRING, multiple=True,
              help='A list of regions; one instance is created per region')
@click.option('--ethermint-version', default="local", help='The hash of ethermints commit or local to use '
                                                           'local version in GOPATH (default)')
@click.option('--master-pkey-name', required=True, help='')
@click.option('--name-root', default="test", help='Root of the names of amis to create')
@click.option('--num-processes', '-n', default=None, type=click.INT,
              help='specify >1 if you want to run instance creation in parallel using multiprocessing')
@click.option('--no-ami-cache', is_flag=True, help='Force rebuilding of Ethermint AMIs')
@click.option('--output-file-path', default="chain.json", help='Output chainshot file path (json)')
def create(regions, ethermint_version, master_pkey_name, name_root, num_processes, no_ami_cache,
           output_file_path):
    """
    Creates an ethermint network consisting of ethermint nodes
    """
    with open(os.path.join(DEFAULT_FILES_LOCATION, master_pkey_name + '.key.pub'), 'r') as f:
        master_pub_key = f.read()
    chainmanager = Chainmanager(num_processes=num_processes)
    chain = chainmanager.create_ethermint_network(regions, ethermint_version, master_pub_key, name_root,
                                                  no_ami_cache=no_ami_cache)

    print(chain)

    with open(output_file_path, 'w') as f:
        json.dump(chain.serialize(), f, indent=2)


@ethermint_testing.command(help='Pass as arguments the list of ethermint instance objects, '
                                'supplied in "region:id" pairs')
@click.option('--name', default="Ethermint-network-chainshot", help='The name of the chainshot')
@click.option('--output-file-path', default="chainshot.json", help='Output chainshot file path (json)')
@click.argument('chain-file', type=click.Path(exists=True))
def chainshot(name, output_file_path, chain_file):
    """
    Allows to create a chainshot of a network consisting of multiple ec2 instances
    """
    with open(chain_file, 'r') as f:
        chain = Chain.deserialize(f.read())
    chainshot_data = Chainshotter().chainshot(name, chain)
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

    chain = Chainshotter(num_processes).thaw(chainshot)
    print(chain)


@ethermint_testing.command(help="check if the consensus on the chain is making progress")
@click.argument('chain-file', type=click.Path(exists=True))
def isalive(chain_file):
    with open(chain_file, 'r') as f:
        chain = Chain.deserialize(json.load(f))
    print(Chainmanager.isalive(chain))


@ethermint_testing.command(help="check the status of all of the nodes that form the chain")
@click.argument('chain-file', type=click.Path(exists=True))
def status(chain_file):
    with open(chain_file, 'r') as f:
        chain = Chain.deserialize(json.loads(f.read()))
    print(json.dumps(Chainmanager.get_status(chain)))


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


@ethermint_testing.command(help="usage: get_roster chain1.json chain2.json...")
@click.argument('chain_files', type=unicode, nargs=-1)
def get_roster(chain_files):
    chain_objects = []
    for chain_file in chain_files:
        with open(chain_file, 'r') as f:
            chain_objects.append(Chain.deserialize(json.loads(f.read())))
    print yaml.dump(Chainmanager().get_roster(chain_objects), default_flow_style=False)


cli = click.CommandCollection(sources=[ethermint_testing])

if __name__ == '__main__':
    cli()
