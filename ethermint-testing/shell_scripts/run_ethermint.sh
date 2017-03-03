#!/usr/bin/env bash
set -eu

# this is the nodes id - determines which validator json to use
ID=$1

# if passed, second argument should be a tendermint-compatible list of seed node addresses
if [ $# -eq 1 ] ; then
    SEEDS=
else
    SEEDS="--seeds $2"
fi

# TODO
#cp priv_validator.json.$ID /ethermint/data/priv_validator.json
#
#ethermint --datadir /ethermint/data \
#    --rpc --rpcaddr=0.0.0.0 --rpcapi "eth,net,web3,personal" \
#    $SEEDS
