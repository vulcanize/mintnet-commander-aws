#!/usr/bin/env bash

set -euo xtrace

# wait for ec2 to become fully up
echo "waiting 180 seconds for cloud-init to update /etc/apt/sources.list"
timeout 180 /bin/bash -c \
  'until stat /var/lib/cloud/instance/boot-finished 2>/dev/null; do echo waiting ...; sleep 1; done'
echo "running apt-get update ..."
cat /etc/apt/sources.list
sudo -E apt-get -y update

sudo apt-get install -y build-essential git python

# install and turn on NTP to be used to synchronize time across machines
sudo apt-get install -y ntp ntpdate sysv-rc-conf
sudo sysv-rc-conf ntpd on
ntpq -p  # check peers list

# install golang 1.7
sudo curl -O https://storage.googleapis.com/golang/go1.7.4.linux-amd64.tar.gz
sudo tar -xf go1.7.4.linux-amd64.tar.gz
sudo mv go /usr/local
export GOROOT=/usr/local/go
export PATH=$GOROOT/bin:$PATH

go version

# prepare GOPATH
mkdir -p $HOME/go
export GOPATH=$HOME/go
mkdir -p $GOPATH/src $GOPATH/bin
sudo chown -R ubuntu:ubuntu $HOME
export PATH=$GOPATH/bin:$PATH

echo "export GOROOT=/usr/local/go" >> $HOME/.bashrc
echo "export GOPATH=$HOME/go" >> $HOME/.bashrc
echo "export PATH=$HOME/go/bin:/usr/local/go/bin:$PATH" >> $HOME/.bashrc

# install libusb (used by geth to support usb devices)
sudo apt-get install libusb-dev

go get github.com/tendermint/ethermint/cmd/ethermint

# user must pass certain ethermint version by providing a commit hash
echo "Using ethermint $ETHERMINT"
git -C $GOPATH/src/github.com/tendermint/ethermint checkout $ETHERMINT
go install -x github.com/tendermint/ethermint/cmd/ethermint
