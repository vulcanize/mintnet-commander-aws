import os
import shutil

import boto3
import pytest
from moto import mock_ec2
from os.path import join, dirname

from chainmaker import Chainmaker
from settings import DEFAULT_REGION, DEFAULT_DEVICE
from utils import get_shh_key_file

NETWORK_SIZE = 4


@pytest.fixture()
def fake_ethermint_files(tmp_dir):
    dest = join(tmp_dir, "ethermint", "priv_validator.json.{}")
    os.makedirs(dirname(dest))
    for i in xrange(NETWORK_SIZE):
        shutil.copyfile("tests/priv_validator.json.in", dest.format(i+1))
    os.makedirs(join(tmp_dir, "data"))
    shutil.copy("tests/genesis.json", join(tmp_dir, "data"))


@pytest.fixture()
def chainmaker(monkeypatch, mockossystem, tmp_dir, fake_ethermint_files):
    monkeypatch.setattr(os, 'system', mockossystem)
    monkeypatch.setattr('utils.DEFAULT_FILES_LOCATION', tmp_dir)
    monkeypatch.setattr('chainmaker.DEFAULT_FILES_LOCATION', tmp_dir)
    return Chainmaker()


@mock_ec2
def test_creating_ethermint_network(chainmaker):
    ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
    master_ami, minion_ami = "ami-06875e10", "ami-10d50c06"

    master, minions = chainmaker.create_ethermint_network(NETWORK_SIZE, master_ami, minion_ami)
    instances = list(ec2.instances.all())
    assert len(instances) == len(minions) + 1

    # check if master and minions have the correct AMI
    assert master.image_id == master_ami
    for minion in minions:
        assert minion.image_id == minion_ami


@mock_ec2
def test_creating_ethermint_network_failures(chainmaker):
    pass


@mock_ec2
def test_ethermint_network_security_group(chainmaker):
    # test if nodes in the network can talk to each other (are in the same security group)
    master_ami, minion_ami = "ami-06875e10", "ami-10d50c06"
    master, minions = chainmaker.create_ethermint_network(NETWORK_SIZE, master_ami, minion_ami)

    master_sec_groups = [group["GroupName"] for group in master.security_groups]
    assert len(master_sec_groups) == 1

    for minion in minions:
        minion_sec_groups = [group["GroupName"] for group in minion.security_groups]
        assert len(minion_sec_groups) == 1
        assert minion_sec_groups == master_sec_groups


@mock_ec2
def test_ethermint_network_attaches_volumes(chainmaker):
    master_ami, minion_ami = "ami-06875e10", "ami-10d50c06"
    master, minions = chainmaker.create_ethermint_network(NETWORK_SIZE, master_ami, minion_ami)

    for minion in minions:
        assert len(minion.block_device_mappings) == 2  # the default drive and our additional drive
        found_our_volume = False
        for bdm in minion.block_device_mappings:
            if bdm["DeviceName"] == DEFAULT_DEVICE:
                found_our_volume = True
                break
        assert found_our_volume


@mock_ec2
def test_ethermint_network_mounts_volumes(chainmaker, mockossystem):
    # mount has to be done manually since the boto3 interface does not allow to do this
    # for now, testing if ssh command is correct
    master_ami, minion_ami = "ami-06875e10", "ami-10d50c06"
    master, minions = chainmaker.create_ethermint_network(NETWORK_SIZE, master_ami, minion_ami)

    for minion in minions:
        mockossystem.assert_any_call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                     "'bash -s' < shell_scripts/mount_new_volume.sh".format(
            get_shh_key_file(minion.key_name), minion.public_ip_address))
