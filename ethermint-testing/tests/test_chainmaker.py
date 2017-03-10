import os
import shutil
from os.path import join, dirname

import boto3
import pytest
import yaml

from chainmaker import Chainmaker
from settings import DEFAULT_REGION, DEFAULT_DEVICE
from utils import get_shh_key_file

NETWORK_SIZE = 4


@pytest.fixture()
def fake_ethermint_files(tmp_dir):
    dest = join(tmp_dir, "ethermint", "priv_validator.json.{}")
    os.makedirs(dirname(dest))
    testsdir = os.path.dirname(os.path.realpath(__file__))
    for i in xrange(NETWORK_SIZE):
        shutil.copyfile(os.path.join(testsdir, "priv_validator.json.in"), dest.format(i+1))
    dest_datadir = join(tmp_dir, "ethermint", "data")
    os.makedirs(dest_datadir)
    shutil.copy(os.path.join(testsdir, "genesis.json"), dest_datadir)


@pytest.fixture()
def chainmaker(monkeypatch, mockossystem, tmp_dir, fake_ethermint_files, moto):
    monkeypatch.setattr(os, 'system', mockossystem)
    monkeypatch.setattr('utils.DEFAULT_FILES_LOCATION', tmp_dir)
    monkeypatch.setattr('chainmaker.DEFAULT_FILES_LOCATION', tmp_dir)
    return Chainmaker()


def test_creating_ethermint_network(chainmaker):
    ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
    ami = "ami-10d50c06"

    nodes = chainmaker.create_ethermint_network(NETWORK_SIZE, ami)
    assert len(list(ec2.instances.all())) == len(nodes)

    # check if nodes have the correct AMI
    for node in nodes:
        assert node.image_id == ami


def test_creating_ethermint_network_failures(chainmaker):
    pass


def test_ethermint_network_security_group(chainmaker):
    # test if nodes in the network can talk to each other (are in the same security group)
    ami = "ami-10d50c06"
    nodes = chainmaker.create_ethermint_network(NETWORK_SIZE, ami)

    for node in nodes:
        node_sec_groups = [group["GroupName"] for group in node.security_groups]
        assert len(node_sec_groups) == 1


def test_ethermint_network_attaches_volumes(chainmaker):
    ami = "ami-10d50c06"
    nodes = chainmaker.create_ethermint_network(NETWORK_SIZE, ami)

    for node in nodes:
        assert len(node.block_device_mappings) == 2  # the default drive and our additional drive
        found_our_volume = False
        for bdm in node.block_device_mappings:
            if bdm["DeviceName"] == DEFAULT_DEVICE:
                found_our_volume = True
                break
        assert found_our_volume


def test_ethermint_network_mounts_volumes(chainmaker, mockossystem):
    # mount has to be done manually since the boto3 interface does not allow to do this
    # for now, testing if ssh command is correct
    ami = "ami-10d50c06"
    nodes = chainmaker.create_ethermint_network(NETWORK_SIZE, ami)

    for node in nodes:
        mockossystem.assert_any_call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                     "'bash -s' < shell_scripts/mount_new_volume.sh".format(
            get_shh_key_file(node.key_name), node.public_ip_address))


def test_ethermint_network_update_roster(chainmaker, mockossystem):
    ami = "ami-10d50c06"
    nodes = chainmaker.create_ethermint_network(NETWORK_SIZE, ami, True)
    nodes_ips = [node.public_ip_address for node in nodes]

    filepath = None
    sh_command_start = "shell_scripts/copy_roster.sh"
    for c in mockossystem.mock_calls:
        first_arg = c[1][0]
        if first_arg.startswith(sh_command_start):
            filepath = first_arg[first_arg.find(sh_command_start) + len(sh_command_start):].strip()
            break
    assert filepath

    with open(filepath, "r") as f:
        contents = yaml.safe_load(f)

    for c in contents:
        assert contents[c]['host'] in nodes_ips
