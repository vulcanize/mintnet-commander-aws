#!/usr/bin/env bash
set -euo xtrace

# format to ext4
sudo mkfs -t ext4 /dev/xvdh

# create dir to mount to
sudo mkdir /ethermint

# mount as /ethermint
sudo mount /dev/xvdh /ethermint

# allow user ubuntu to write to it
sudo chown ubuntu /ethermint
