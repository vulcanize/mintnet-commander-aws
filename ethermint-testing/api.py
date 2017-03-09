import json
import logging
import os

import click

from amibuilder import AMIBuilder
from chainmaker import Chainmaker
from chainshotter import Chainshotter
from settings import DEFAULT_FILES_LOCATION

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
@click.option('--update-roster/--no-update-roster', default=False, help='Update /etc/salt/roster locally?')
@click.option('--regions', required=True, default=[], type=click.STRING, multiple=True,
              help='A list of regions; one instance is created per region')
@click.option('--ethermint-version', default="HEAD", help='The hash of ethermints commit')
@click.option('--master-pkey-name', required=True, help='')
@click.option('--name-root', default="test", help='Root of the names of amis to create')
@pass_environment
def create(env, update_roster, regions, ethermint_version, master_pkey_name, name_root):
    """
    Creates an ethermint network consisting of ethermint nodes
    """
    with open(os.path.join(DEFAULT_FILES_LOCATION, master_pkey_name + '.key.pub'), 'r') as f:
        master_pub_key = f.read()
    return env.chainmaker.create_ethermint_network(regions, ethermint_version, master_pub_key, update_roster, name_root)


@ethermint_testing.command()
@click.option('--name', default="Ethermint-network-chainshot", help='The name of the chainshot')
@click.option('--instances', required=True, default=[], type=click.STRING,
              multiple=True, help='The list of ethermint instance objects')
@click.option('--output-file-path', default="chainshot.json", help='Output chainshot file path (json)')
@pass_environment
def chainshot(env, name, instances, output_file_path):
    """
    Allows to create a chainshot of a network consisting of multiple ec2 instances
    """
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
        return instances


cli = click.CommandCollection(sources=[ethermint_testing])

if __name__ == '__main__':
    cli()
