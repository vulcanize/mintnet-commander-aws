# A utility script designed to be run within oc_ethermint docker containers
# It handles merging priv_validator.json files into a genesis.json file (Tendermint)
import json
import os


def prepare_validators(num_validators, output_dir):
    os.system("ethermint -datadir {} init {}".format(os.path.join(output_dir, "data/"),
                                                     "$GOPATH/src/github.com/tendermint/ethermint/docker/genesis.json"))
    for i in range(1, num_validators + 1):
        filename = "priv_validator.json.{}".format(i)
        output_path = os.path.join(output_dir, filename)
        os.system("tendermint gen_validator | tail -n +3 > {}".format(output_path))


def fill_validators(num_validators, genesis_file, new_genesis_file, output_dir):

    validators = []

    for i in range(1, num_validators+1):
        with open(os.path.join(output_dir, 'priv_validator.json.%s' % i)) as f:
            validator = json.loads(f.read())
            pub_key = validator['pub_key']

            validators.append(dict(amount=10,
                                   name="",
                                   pub_key=pub_key))

    with open(genesis_file) as f:
        genesis = json.loads(f.read())
        genesis['validators'] = validators
        print(genesis)

    print(new_genesis_file)
    with open(new_genesis_file, 'w') as f:
        f.write(json.dumps(genesis))
