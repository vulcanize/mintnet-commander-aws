import os

import boto3
import pytest
from mock import MagicMock
from moto import mock_ec2

from chainmaker import Chainmaker
from settings import DEFAULT_REGION, DEFAULT_DEVICE
from utils import get_shh_key_file


@pytest.fixture()
def chainmaker(monkeypatch, mockossystem, tmp_dir):
    monkeypatch.setattr(os, 'system', mockossystem)
    monkeypatch.setattr(os.path, 'exists', lambda path: True)
    monkeypatch.setattr('chainmaker.create_keyfile', MagicMock(return_value="keyfile"))
    monkeypatch.setattr('chainmaker.DEFAULT_FILES_LOCATION', tmp_dir)
    return Chainmaker()


@mock_ec2
def test_creating_ethermint_network(chainmaker):
    ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
    master_ami, minion_ami = "ami-06875e10", "ami-10d50c06"

    master, minions = chainmaker.create_ethermint_network(4, master_ami, minion_ami)
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
    master, minions = chainmaker.create_ethermint_network(4, master_ami, minion_ami)

    master_sec_groups = [group["GroupName"] for group in master.security_groups]
    assert len(master_sec_groups) == 1

    for minion in minions:
        minion_sec_groups = [group["GroupName"] for group in minion.security_groups]
        assert len(minion_sec_groups) == 1
        assert minion_sec_groups == master_sec_groups


@mock_ec2
def test_ethermint_network_attaches_volumes(chainmaker):
    ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
    master_ami, minion_ami = "ami-06875e10", "ami-10d50c06"
    master, minions = chainmaker.create_ethermint_network(4, master_ami, minion_ami)

    for minion in minions:
        volume = ec2.Volume(minion.block_device_mappings[0]["Ebs"]["VolumeId"])
        assert volume.attachments[0]["InstanceId"] == minion.id
        assert minion.block_device_mappings[1]["DeviceName"] == DEFAULT_DEVICE


@mock_ec2
def test_ethermint_network_mounts_volumes(chainmaker, mockossystem):
    # mount has to be done manually since the boto3 interface does not allow to do this
    # for now, testing if ssh command is correct
    master_ami, minion_ami = "ami-06875e10", "ami-10d50c06"
    master, minions = chainmaker.create_ethermint_network(4, master_ami, minion_ami)

    for minion in minions:
        mockossystem.assert_any_call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                     "'bash -s' < shell_scripts/mount_new_volume.sh".format(
            get_shh_key_file(minion.key_name), minion.public_ip_address))
