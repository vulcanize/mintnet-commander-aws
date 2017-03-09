#!/usr/bin/env bash

export GOPATH=$HOME/go

mkdir -p /ethermint/setup /ethermint/data
cp $GOPATH/src/github.com/tendermint/ethermint/docker/genesis.json /ethermint/setup/genesis.json
cp -r $GOPATH/src/github.com/tendermint/ethermint/docker/keystore /ethermint/data/keystore
