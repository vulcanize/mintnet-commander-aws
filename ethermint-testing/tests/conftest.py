import subprocess
from datetime import datetime

import boto3
import os
import pytest
from mock import MagicMock
from moto import mock_ec2

from chainshotter import RegionInstancePair
from settings import DEFAULT_REGION, DEFAULT_INSTANCE_TYPE

SECURITY_GROUP_NAME = "securitygroup"


@pytest.fixture()
def mockami():
    return "ami-90b01686"


@pytest.fixture()
def moto():
    mock_ec2().start()
    yield None
    mock_ec2().stop()


@pytest.fixture()
def mockossystem(monkeypatch):
    mock = MagicMock(os.system, return_value=0)
    monkeypatch.setattr(os, 'system', mock)
    return mock


@pytest.fixture()
def mocksubprocess(monkeypatch):
    mock = MagicMock(subprocess.check_output, return_value="")
    monkeypatch.setattr(subprocess, 'check_output', mock)
    return mock


@pytest.fixture()
def mock_security_group(moto, mock_instance_data):
    def ret(region):
        ec2 = boto3.resource('ec2', region_name=region)
        security_group_name = mock_instance_data["security_group_name"]
        groups = list(ec2.security_groups.filter(GroupNames=[security_group_name]))
        if len(groups) > 0:
            g = groups[0]
        else:
            g = ec2.create_security_group(GroupName=security_group_name, Description="test group")
        return g
    return ret


@pytest.fixture()
def mock_instance_data():
    instance = {
        "image_id": "imageID",
        "tags": [
            {
                "Key": "Name",
                "Value": "testinstance"
            }
        ],
        "security_group_name": SECURITY_GROUP_NAME,
        "key_name": "Key",
        "launch_time": datetime.now()
    }
    return instance


@pytest.fixture()
def mock_instance(mock_instance_data, mock_security_group, moto):
    def _mock_instance(region=DEFAULT_REGION):
        ec2 = boto3.resource('ec2', region_name=region)

        instance = ec2.create_instances(ImageId=mock_instance_data["image_id"],
                                        InstanceType=DEFAULT_INSTANCE_TYPE,
                                        MinCount=1,
                                        MaxCount=1,
                                        SecurityGroupIds=[mock_security_group(region).id],
                                        KeyName=mock_instance_data["key_name"])[0]
        instance.create_tags(Tags=mock_instance_data["tags"])
        assert len(list(instance.volumes.all())) == 1
        return instance

    return _mock_instance


@pytest.fixture()
def mock_instances_in_regions(mock_instance_data, moto):
    def _mock_instances(regions):
        instances = []

        sec_groups = {}
        security_group_name = mock_instance_data["security_group_name"]
        for region in set(regions):
            ec2 = boto3.resource('ec2', region_name=region)
            g = ec2.create_security_group(GroupName=security_group_name, Description="test group")
            sec_groups[region] = g.id

        for region in regions:
            ec2 = boto3.resource('ec2', region_name=region)
            instance = ec2.create_instances(ImageId=mock_instance_data["image_id"],
                                            InstanceType=DEFAULT_INSTANCE_TYPE,
                                            MinCount=1,
                                            MaxCount=1,
                                            SecurityGroupIds=[sec_groups[region]],
                                            KeyName=mock_instance_data["key_name"])[0]
            instance.create_tags(Tags=mock_instance_data["tags"])
            assert len(list(instance.volumes.all())) == 1
            instances.append(RegionInstancePair(region, instance.id))
        return instances

    return _mock_instances


@pytest.fixture()
def mock_instances_with_volumes(mock_instances_in_regions, moto):
    def _mock_instances_with_volumes(regions):
        instances = mock_instances_in_regions(regions)
        for pair in instances:
            add_volume_to_instance(pair.instance, pair.region_name)
        return instances

    return _mock_instances_with_volumes


def add_volume_to_instance(instance, region):
    ec2 = boto3.resource('ec2', region_name=region)
    volume = ec2.create_volume(Size=1, AvailabilityZone=region)
    volume.create_tags(Tags=[{'Key': 'Name', 'Value': 'ethermint_volume'}])
    volume.attach_to_instance(InstanceId=instance.id, Device="/device")


@pytest.fixture()
def mock_instance_with_volume(mock_instance, moto):
    def _mock_instance_with_volume():
        instance = mock_instance()
        add_volume_to_instance(instance, DEFAULT_REGION)
        return instance

    return _mock_instance_with_volume


@pytest.fixture()
def mock_aws_credentials(monkeypatch, tmpdir):
    credentials_file = tmpdir.mkdir("awsfiles").join("credentials")
    credentials_file.write("""
[default]
aws_access_key_id = AAAAAAAAAAAAAAAAAAAA
aws_secret_access_key = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
    """)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(credentials_file))


@pytest.fixture()
def tmp_files_dir(tmpdir, monkeypatch):
    dir = str(tmpdir.mkdir("files"))
    monkeypatch.setattr('utils.DEFAULT_FILES_LOCATION', dir)
    monkeypatch.setattr('chainmaker.DEFAULT_FILES_LOCATION', dir)
    return dir


@pytest.fixture()
def mockregions():
    return ["ap-northeast-1", "ap-northeast-1", "ap-northeast-1", "eu-central-1", "us-west-1", "us-west-1"]
