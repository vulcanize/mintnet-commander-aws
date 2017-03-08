# ethermint-testing
Tools to run [ethermint](https://github.com/tendermint/ethermint) network tests

## Preparations

Make sure AWS credentials are stored in the default directory. To do this, run

```bash
aws configure
```

and provide your Access key. This saves the key in the default system location in `/home/<user>/.aws/credentials`.

Install tendermint and ethermint:

```bash
go install -x github.com/tendermint/ethermint/vendor/github.com/tendermint/tendermint/cmd/tendermint
go install github.com/tendermint/ethermint/cmd/ethermint
```

## Example usage

Go to `ethermint-testing` directory, and then:

0. Create a master key which will be used in salt-ssh orchestration

```bash
python api.py create_master_keys --name <master-key-name>
```

the command saves a key pair to the default location.

1. Run
 
```bash 
python api.py create_amis --master-pkey-name <master-key-name>
```

providing the name from above. The command outputs the IDs of AMIs that were created.
Please note that creating an AMI also creates a snapshot in EC2.

2. Using the newly created AMIs, create an ethermint network:

```bash
python api.py create --count <NR_OF_INSTANCES> --master-ami <master-ami-id> --ethermint-node-ami <minion-ami-id>
```

Parameter `count` defines how many ethermint nodes should be run. AMIs indicate AMI ID's to be used when spinning up new EC2 instances.

After running this command, a network is running in AWS.

## Chainshotting, thawing

A network can be chainshot (a snapshot of each node's chain information can be saved) and later thawed from a chainshot.

To chainshot a network, one needs to list all of the instance IDs which create the network:

```bash
python api.py chainshot --instances <INSTANCE_1_ID> --instances <INSTANCE_2_ID> --instances <INSTANCE_3_ID>
```

This command creates a file called `chainshot.json` in the working directory. Note that the master node cannot be chainshot.

Thawing can be done using said file like so:

```bash
python api.py thaw <FILENAME>
```

Running the following creates new instances from snapshots. This does not recreate the master node. TODO

## Orchestrating

We use saltstack-ssh to orchestrate all ethermint instances. Salt-master is running on master instance and is configured to be able to call other nodes.
To use salt-ssh, first log into the master node using ssh:

```bash
ssh -i files/<master-key>.pem ubuntu@<master-public-IP>
```

and then you can:

```bash
sudo salt-ssh --priv ~/.ssh/master_key -i "*" test.ping
```

which will ping all the instances and collect results.