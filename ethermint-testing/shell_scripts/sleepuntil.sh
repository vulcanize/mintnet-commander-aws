#!/usr/bin/env bash
set -euo xtrace

# example usage: ./shell_scripts/sleepuntil.sh 2017-03-30T14:53:37.425708353

current_epoch=$(date +%s.%N)
target_epoch=$(date -d $1 +%s.%N)

sleep_seconds=$(echo "$target_epoch - $current_epoch"|bc)

sleep $sleep_seconds
