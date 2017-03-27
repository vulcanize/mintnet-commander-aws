#!/usr/bin/env bash
set -euo xtrace

sudo mv /ethermint/ntp_conf /etc/ntp.conf

sudo service ntp restart
