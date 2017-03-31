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

## Input/Output formats by example

1. `create`
  - input: list of AWS regions given in commandline: `-r us-east-1 -r -us-west-1 -r -us-west-1 ...`
  - output: chain `.json` file:
  
    ```
    {
      "instances": [
        {
          "instance": {
            "key_name": "salt-instance-1490723614_e7752aa786bc4f2b901c5cdf11a47e26", 
            "region": "us-west-1", 
            "id": "i-06f49a63e848bcb6f"
          }
        }, ...
      ], 
      "type": "ethermint", 
      "name": ""
    }
    ```
        
  - output: ssh key `.pem` file 
2. `chainshot`
  - input: chain `.json` file
  - output: chainshot `.json` file
  
    ```
    {
      "instances": [
        {
          "instance": {
            "availablility_zone": "us-west-1b", 
            "ami": "ami-29a3f849", 
            "key_name": "salt-instance-1490723614_e7752aa786bc4f2b901c5cdf11a47e26", 
            "tags": [
              {
                "Value": "test-ethermint-ami-29a3f8490", 
                "Key": "Name"
              }
            ], 
            "vpc_id": "vpc-0835e76c", 
            "region": "us-west-1", 
            "id": "i-06f49a63e848bcb6f", 
            "security_groups": [
              "ethermint-security_group-salt-ssh-2017-03-28 19:53:27.612893"
            ]
          }, 
          "snapshot": {
            "to": "2017-03-30T12:03:54+00:00", 
            "from": "2017-03-28T17:53:35+00:00", 
            "id": "snap-08358ddeefd7a0ec8"
          }
        }, ...
      ], 
      "chainshot_name": "Ethermint-network-chainshot"
    }
    ```
3. `thaw`
  - input: chainshot `.json` file
  - output: chain `.json` file
4. `status`
  - input: chain `.json` file (or files for `roster`)
  - output: status `.json`
  
    ```
    {
       "is_alive" : true,
       "height" : 107338,
       "nodes" : [
          {
             "instance_region" : "us-west-1",
             "is_alive" : true,
             "last_block_time" : "2017-03-30T14:13:12.993000+0000",
             "instance_id" : "i-06f49a63e848bcb6f",
             "name" : "test-ethermint-ami-29a3f8490",
             "height" : 107337,
             "last_block_height" : 107337
          }, ...
       ],
       "age" : null
    }
    ```

5. `history`
  - input: chain `.json` file (or files for `roster`)
  - output: history `.csv` (? - WIP)
6. `roster`
  - input: chain `.json` file (or files for `roster`)
  - output: salt-ssh [roster YAML](https://docs.saltstack.com/en/latest/topics/ssh/roster.html) 
7. `isalive`
  - input: chain `.json` file (or files for `roster`)
  - output: `True` / `False`

## Todo overview

**TODO** make issues out of this?

 - rethink input/output formats
 - proper organization of chain/chainshot data like: chain names, tags on aws, ethermint versions, keys, owners
 - using a fork of `ethermint`
 - using remote `ethermint` install to `ethermint init`
 - same for `tenderint gen_validator`?
 - installing a different version of `ethermint` on `thaw`
 