#!/usr/bin/env bash
set -euo xtrace

sudo rm /etc/salt/roster
sudo mv $1 /etc/salt/roster
