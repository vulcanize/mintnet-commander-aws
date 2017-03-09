#!/usr/bin/env bash
set -euo xtrace

export GOPATH=$HOME/go

if [ $# -eq 0 ] ; then
    SEEDS=
else
    SEEDS="--seeds $1"
fi

nohup $GOPATH/bin/ethermint --datadir /ethermint/data \
    --rpc --rpcaddr=0.0.0.0 --rpcapi "eth,net,web3,personal" \
    $SEEDS > /ethermint/data/ethermint.log 2>&1 &
