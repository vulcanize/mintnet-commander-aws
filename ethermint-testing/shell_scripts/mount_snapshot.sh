#!/usr/bin/env bash
set -euo xtrace

# create dir to mount to
sudo mkdir /ethermint

# mount snapshot to /ethermint
sudo mount /dev/xvdh /ethermint
