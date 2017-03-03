# ethermint-testing
Tools to run [ethermint](https://github.com/tendermint/ethermint) network tests

## Preparations

Make sure AWS credentials are stored in the default directory. To do this, run

```bash
aws configure
```

and provide your Access key. This saves the key in the default system location in `/home/<user>/.aws/credentials`.

## Example usage

Go to `ethermint-testing` directory, and then:

1. Run 
```bash 
python api.py create_amis
```

which outputs the IDs of AMIs that were created.
Please note that creating an AMI also creates a snapshot in EC2.

2. Using the newly created AMIs, create an ethermint network:

```bash
python api.py create --count 3 --master-ami <master-ami-id> --ethermint-node-ami <minion-ami-id>
```

Parameter `count` defines how many ethermint nodes should be run. AMIs indicate AMI ID's to be used when spinning up new EC2 instances.

3. 