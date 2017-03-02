import os

import boto3
import pytest
from moto import mock_ec2

from chainmaker import Chainmaker
from settings import DEFAULT_REGION
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
