#!/usr/bin/env bash
set -euo xtrace

# FIXME: exports like this shouldn't really be needed, but .bashrc is not executed on non-interractive ssh logins
# what's the elegant fix?
export GOPATH=$HOME/go

git -C $GOPATH/src/github.com/tendermint/ethermint rev-parse HEAD
