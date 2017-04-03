#!/usr/bin/env bash
set -euo xtrace

num_steps=$1
delay_step=$2
interval=$3
interface=$4
start_at=$5

# sleeping until a given exact datetime for synchronization
current_epoch=$(date +%s.%N)
target_epoch=$(date -d $start_at +%s.%N)
sleep_seconds=$(echo "$target_epoch - $current_epoch"|bc)
sleep $sleep_seconds

# first delay, no need to delete previous netem command
delay_miliseconds=$delay_step
sudo tc qdisc add dev $interface root netem delay ${delay_miliseconds}ms
date '+%Y-%m-%dT%H:%M:%S.%N'
sleep $interval

# next delays - calculate, delete previous, set next, sleep
for i in `seq 2 $num_steps`; do
    delay_miliseconds=$(echo "$i * $delay_step"|bc)
    sudo tc qdisc del dev $interface root netem
    sudo tc qdisc add dev $interface root netem delay ${delay_miliseconds}ms
    date '+%Y-%m-%dT%H:%M:%S.%N'
    sleep $interval
done

sudo tc qdisc del dev $interface root netem
date '+%Y-%m-%dT%H:%M:%S.%N'
