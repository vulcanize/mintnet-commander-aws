#!/usr/bin/env bash

set -x

# wait for ec2 to become fully up
echo "waiting 180 seconds for cloud-init to update /etc/apt/sources.list"
timeout 180 /bin/bash -c \
  'until stat /var/lib/cloud/instance/boot-finished 2>/dev/null; do echo waiting ...; sleep 1; done'
echo "running apt-get update ..."
cat /etc/apt/sources.list
sudo -E apt-get -y update

# install salt
sudo add-apt-repository -y ppa:saltstack/salt
sudo -E apt-get -y update
sudo apt-get install -y salt-ssh

sudo apt-get install -y build-essential git python

# install golang 1.7
sudo curl -O https://storage.googleapis.com/golang/go1.7.4.linux-amd64.tar.gz
sudo tar -xvf go1.7.4.linux-amd64.tar.gz
sudo mv go /usr/local
go version

# prepare GOPATH
export GOROOT=/usr/local/go
mkdir -p $HOME/go
export GOPATH=$HOME/go
mkdir -p $GOPATH/src $GOPATH/bin
sudo chmod -R 777 $GOPATH
export PATH=$GOPATH/bin:/usr/local/go/bin:$PATH

echo "export GOROOT=/usr/local/go" >> $HOME/.bashrc
echo "export GOPATH=$HOME/go" >> $HOME/.bashrc
echo "export PATH=$HOME/go/bin:/usr/local/go/bin:$PATH" >> $HOME/.bashrc

# install libusb (used by geth to support usb devices)
sudo apt-get install libusb-dev

go get github.com/tendermint/ethermint/cmd/ethermint
