# A utility script designed to be run within oc_ethermint docker containers
# It handles merging priv_validator.json files into a genesis.json file (Tendermint)
import json
import argparse

TENDERMINT_GENESIS_JSON_PATH = '/ethermint/data/genesis.json'

# NOTE: using argparse to be able to use this in go-lang containers
parser = argparse.ArgumentParser(description='Preprocess Tendermint\'s json files.')
parser.add_argument('--num-validators', type=int,
                    help='Number of validators to configure for')
parser.add_argument('--output', type=str, default=TENDERMINT_GENESIS_JSON_PATH,
                    help='Output/Input path to ethermint genesis.json')

args = parser.parse_args()


def fill_validators(num_validators, output):

    validators = []

    for i in xrange(1, num_validators+1):
        with open('priv_validator.json.%s' % i) as f:
            validator = json.loads(f.read())
            pub_key = validator['pub_key']

            validators.append(dict(amount=10,
                                   name="",
                                   pub_key=pub_key))

    with open(output) as f:
        genesis = json.loads(f.read())
        genesis['validators'] = validators

    with open(output, 'w') as f:
        f.write(json.dumps(genesis))


if __name__ == "__main__":
    fill_validators(num_validators=args.num_validators,
                    output=args.output)
