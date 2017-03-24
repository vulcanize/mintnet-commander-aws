# ethermint-testing
Tools to orchestrate and run [ethermint](https://github.com/tendermint/ethermint) network tests

## Preparations

1. Make sure AWS credentials are stored in the default directory.
2. Install [packer](https://www.packer.io/)
2. Install tendermint and ethermint:

```bash
go install github.com/tendermint/ethermint/cmd/ethermint
go install github.com/tendermint/ethermint/vendor/github.com/tendermint/tendermint/cmd/tendermint
```
3. Clone repo and `pip install -r requirements.txt`
4. Make sure `tendermint`, `ethermint`, `packer` are in your path

## Quickstart

From `ethermint-testing` directory:

### Creating

Create an ethermint network spanning 2 regions:

```bash
python api.py create -r us-west-1 -r us-east-1 --output-file-path files/chain1.json
```

Relevant data about the chain are dumped to the json file. Use this file to reference the chain in subsequent commands.

After running this command, a network is running in AWS.

### Chainshotting, thawing

A network can be chainshot (a snapshot of each node's chain data can be saved) and later thawed from a chainshot.

To chainshot a network:

```bash
python api.py chainshot --output-file-path files/chainshot1.json files/chain1.json
```

Thawing can be done using the chainshot file like so:

```bash
python api.py thaw --output-file-path files/thawed_chain1.json files/chainshot1.json
```

Thawing creates new instances from snapshots, loads the chain data snapshots and resumes the consensus process.

### Salt-ssh

To generate a roster file from a set of chains for processing using `salt-ssh` do:

```bash
python api.py roster files/chain1.json > files/roster
```
and then:
```bash
sudo salt-ssh --roster-file=files/roster --priv <PATH TO PRIV KEY> -i '*' test.ping
```

### Isalive and status

To quickly check the liveness of a chain:
```bash
python api.py isalive files/chain1.json
```
or to get more elaborate status report:
```bash
python api.py status files/chain1.json
```

## Todo overview

**TODO** make issues out of this?

 - using a fork of `ethermint`
 - using remote `ethermint` install to `ethermint init`
 - same for `tenderint gen_validator`?
 - installing a different version of `ethermint` on `thaw`
 - proper organization of chain/chainshot data like: chain names, tags on aws, ethermint versions, keys, owners
 - `ntp` to get rid of time offsets on ec2
 