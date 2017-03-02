import json
import logging
import click

from chainmaker import Chainmaker
from chainshotter import Chainshotter


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
@click.option('--master-ami', default=None, help='The AMI to be used for the master node')
@click.option('--ethermint-node-ami', default=None, help='The AMI to be used for ethermint nodes')
@click.option('--security-group-name', default=None, help='The security group name to be used')
@pass_environment
def create(env, count, master_ami, ethermint_node_ami, security_group_name):
    """
    Creates an ethermint network consisting of 1 master node and some ethermint nodes
    """
    return env.chainmaker.create_ethermint_network(count, master_ami, ethermint_node_ami, security_group_name)


@ethermint_testing.command()
@click.option('--name', default="Ethermint-network-chainshot", help='The name of the chainshot')
@click.option('--instaces', default=[], help='The list of instance objects')
@click.option('--output-file-path', default="chainshot.json", help='Output chainshot file path (json)')
@pass_environment
def chainshot(env, name, instaces, output_file_path):
    """
    Allows to create a chainshot of a network consisting of multiple ec2 instances
    Instances should contain the master node
    """
    chainshot_data = env.chainshotter.chainshot(name, instaces)
    with open(output_file_path, 'w') as f:
        json.dump(chainshot_data, f, indent=2)


@ethermint_testing.command()
@click.argument('chainshot-file', type=click.Path(exists=True))
@pass_environment
def thaw(env, chainshot_file):
    """
    Allows to unfreeze a network from a config
    """
    with open(chainshot_file) as json_data:
        chainshot = json.load(json_data)
        return env.chainshotter.thaw(chainshot)


cli = click.CommandCollection(sources=[ethermint_testing])

if __name__ == '__main__':
    cli()
