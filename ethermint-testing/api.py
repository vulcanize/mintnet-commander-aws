import json
import logging

import click
import yaml

from chain import Chain
from chainmanager import Chainmanager
from chainshotter import Chainshotter

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@click.group()
def ethermint_testing():
    pass


@ethermint_testing.command(help="Creates an ethermint network in aws regions")
@click.option('--regions', '-r', required=True, default=None, type=click.STRING, multiple=True,
              help='A list of regions; one instance is created per region')
@click.option('--ethermint-version', default="local", help='The hash of ethermints commit or local to use '
                                                           'local version in GOPATH (default)')
@click.option('--name-root', default="test", help='Root of the names of amis to create')
@click.option('--num-processes', '-n', default=None, type=click.INT,
              help='specify >1 if you want to run instance creation in parallel using multiprocessing')
@click.option('--no-ami-cache', is_flag=True, help='Force rebuilding of Ethermint AMIs')
@click.argument('chain-file', type=click.File('wb'))
def create(regions, ethermint_version, name_root, num_processes, no_ami_cache, chain_file):
    chainmanager = Chainmanager(num_processes=num_processes)
    chain = chainmanager.create_ethermint_network(regions, ethermint_version, name_root,
                                                  no_ami_cache=no_ami_cache)

    chain_file.write(json.dumps(chain.serialize()))

    logger.info("Created a chain ".format(chain))


@ethermint_testing.command(help='Makes a snapshot of a chain')
@click.option('--name', default="Ethermint-network-chainshot", help='The name of the chainshot')
@click.argument('chain-file', type=click.File('rb'))
@click.argument('chainshot-file', type=click.File('wb'))
def chainshot(name, chain_file, chainshot_file):
    chain = Chain.deserialize(json.loads(chain_file.read()))
    chainshot_data = Chainshotter().chainshot(name, chain)

    chainshot_file.write(json.dumps(chainshot_data))

    logger.info("The chainshot: {}".format(chainshot_data))


@ethermint_testing.command(help="Unfreezes a network from a chainshot file")
@click.argument('chainshot-file', type=click.File('rb'))
@click.argument('chain-file', type=click.File('wb'))
@click.option('--num-processes', '-n', default=None, type=click.INT,
              help='specify >1 if you want to run instance creation in parallel using multiprocessing')
def thaw(chainshot_file, chain_file, num_processes):
    chainshot = json.loads(chainshot_file.read())

    chain = Chainshotter(num_processes).thaw(chainshot)

    chain_file.write(json.dumps(chain.serialize()))

    logger.info("Thawed a chain {}".format(chain))


@ethermint_testing.command(help="Checks if the consensus on the chain is making progress; for more details, use status")
@click.argument('chain-file', type=click.File('rb'))
def isalive(chain_file):
    chain = Chain.deserialize(json.loads(chain_file.read()))
    print(Chainmanager.isalive(chain))


@ethermint_testing.command(help="Checks the status of all of the nodes that form the chain")
@click.argument('chain-file', type=click.File('rb'))
def status(chain_file):
    chain = Chain.deserialize(json.loads(chain_file.read()))
    print(json.dumps(Chainmanager.get_status(chain)))


@ethermint_testing.command(help="get history of chain performance")
@click.option('--fromm', '-f', default=None, type=click.INT,
              help='earliest block to look at')
@click.option('--to', '-t', default=None, type=click.INT,
              help='last block to look at')
@click.argument('chain-file', type=click.File('rb'))
def history(chain_file, fromm, to):
    chain = Chain.deserialize(json.loads(chain_file.read()))
    to_print = "\n".join([str(c) for c in Chainmanager.get_history(chain, fromm, to)])
    print(to_print)


@ethermint_testing.command(help="get history of chain performance")
@click.option('--num-steps', '-s', default=1, type=click.INT,
              help='number of delay increases to make')
@click.option('--delay-step', '-d', default=100, type=click.INT,
              help='duration of delay to increase by every step (ms)')
@click.option('--interval', '-i', default=5, type=click.INT,
              help='duration of interval between delay increase steps (s)')
@click.argument('chain-file', type=click.File('rb'))
def network_fault(chain_file, num_steps, delay_step, interval):
    chain = Chain.deserialize(json.loads(chain_file.read()))

    result = Chainmanager.get_network_fault(chain, num_steps, delay_step, interval)

    print(json.dumps(result))


@ethermint_testing.command(help="Generates a Salt-ssh roster from multiple chains")
@click.argument('chain_files', type=unicode, nargs=-1)
def roster(chain_files):
    chain_objects = []
    for chain_file in chain_files:
        with open(chain_file, 'r') as json_data:
            chain_objects.append(Chain.deserialize(json.loads(json_data.read())))
    print yaml.dump(Chainmanager().get_roster(chain_objects), default_flow_style=False)


cli = click.CommandCollection(sources=[ethermint_testing])

if __name__ == '__main__':
    cli()
