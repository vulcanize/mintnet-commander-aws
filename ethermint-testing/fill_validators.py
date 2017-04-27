# A utility script designed to be run within oc_ethermint docker containers
# It handles merging priv_validator.json files into a genesis.json file (Tendermint)
import json
import os

ETHERMINT_GETH_GENESIS_JSON = "$GOPATH/src/github.com/tendermint/ethermint/docker/genesis.json"


def call_gen_validator(output_path):
    os.system("tendermint gen_validator > {}".format(output_path))


def call_init(output_dir):
    os.system("ethermint -datadir {} init {}".format(output_dir, ETHERMINT_GETH_GENESIS_JSON))


def prepare_validators(num_validators, output_dir):
    call_init(os.path.join(output_dir, "data"))
    for i in range(1, num_validators + 1):
        filename = "priv_validator.json.{}".format(i)
        output_path = os.path.join(output_dir, filename)
        call_gen_validator(output_path)


def fill_validators(num_validators, genesis_file, new_genesis_file, output_dir):

    validators = []

    for i in range(1, num_validators+1):
        with open(os.path.join(output_dir, 'priv_validator.json.%s' % i), "r") as f:
            validator = json.loads(f.read())
            pub_key = validator['pub_key']

            validators.append(dict(amount=10,
                                   name="",
                                   pub_key=pub_key))

    with open(genesis_file) as f:
        genesis = json.loads(f.read())
        genesis['validators'] = validators

    with open(new_genesis_file, 'w') as f:
        f.write(json.dumps(genesis))
