import os

import boto3
import pytest
from moto import mock_ec2

from chainmaker import Chainmaker
from settings import DEFAULT_REGION, DEFAULT_DEVICE
from utils import get_shh_key_file


@pytest.fixture()
def chainmaker(monkeypatch, mockossystem):
    monkeypatch.setattr(os, 'system', mockossystem)
    monkeypatch.setattr(os.path, 'exists', lambda path: True)
    return Chainmaker()


@mock_ec2
def test_security_group_creation(chainmaker):
    security_group_name = "security_group"
    ports = [i for i in range(8000, 8005)]
    group = chainmaker.create_security_group(security_group_name, ports)
    ec2_client = boto3.client('ec2', region_name=DEFAULT_REGION)
    groups = ec2_client.describe_security_groups(Filters=[{'Name': "group-name", 'Values': [security_group_name]}])
    assert len(groups["SecurityGroups"]) == 1
    ip_permissions = groups["SecurityGroups"][0]["IpPermissions"]
    assert len(ip_permissions) == len(ports)
    for perm in ip_permissions:
        assert perm["ToPort"] == perm["FromPort"]
        assert perm["ToPort"] in ports
    assert groups["SecurityGroups"][0]["GroupId"] == group.id


@mock_ec2
def test_adding_volume_to_instance(chainmaker, mock_instance):
    instance = mock_instance()
    volumes_before = list(instance.volumes.all())
    chainmaker.add_volume(instance)
    volumes_after = list(instance.volumes.all())
    assert len(volumes_after) == len(volumes_before) + 1

    new_volume = set(volumes_after) - set(volumes_before)
    assert list(new_volume)[0].attachments[0]["InstanceId"] == instance.id

    # make sure the device is exposed correctly
    assert instance.block_device_mappings[1]["DeviceName"] == DEFAULT_DEVICE


@mock_ec2
def test_added_volume_mounted(chainmaker, mock_instance, mockossystem):
    # mount has to be done manually since the boto3 interface does not allow to do this
    # for now, testing if ssh command is correct
    instance = mock_instance()
    chainmaker.add_volume(instance)
    mockossystem.assert_called_once_with("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                         "'bash -s' < mount_new_volume.sh".format(get_shh_key_file(instance.key_name),
                                                                                  instance.public_ip_address))


@mock_ec2
def test_adding_volume_failures():
    pass


@mock_ec2
def test_creating_from_json():
    pass


@mock_ec2
def test_creating_from_json_failures():
    pass


@mock_ec2
def test_creating_ethermint_network(chainmaker):
    master_ami, minion_ami = "ami-06875e10", "ami-10d50c06"

    master, minions = chainmaker.create_ethermint_network(4, master_ami, minion_ami)
    ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
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
    master_ami, minion_ami = "ami-06875e10", "ami-10d50c06"
    master, minions = chainmaker.create_ethermint_network(4, master_ami, minion_ami)

    for minion in minions:
        volume = minion.block_device_mappings[0]["Ebs"]["VolumeId"]
        assert volume.attachments[0]["InstanceId"] == minion.id
        assert minion.block_device_mappings[1]["DeviceName"] == DEFAULT_DEVICE
