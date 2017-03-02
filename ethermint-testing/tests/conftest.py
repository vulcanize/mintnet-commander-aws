from datetime import datetime

import boto3
import pytest

from settings import DEFAULT_REGION, DEFAULT_INSTANCE_TYPE


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
        "security_group_name": "securitygroup",
        "key_name": "Key",
        "launch_time": datetime.now()
    }
    return instance


@pytest.fixture()
def mock_instance(mock_instance_data):
    def _mock_instance():
        ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)

        security_group_name = mock_instance_data["security_group_name"]
        g = ec2.create_security_group(GroupName=security_group_name, Description="test group")

        instance = ec2.create_instances(ImageId=mock_instance_data["image_id"],
                                        InstanceType=DEFAULT_INSTANCE_TYPE,
                                        MinCount=1,
                                        MaxCount=1,
                                        SecurityGroupIds=[g.id],
                                        KeyName=mock_instance_data["key_name"])[0]
        instance.create_tags(Tags=mock_instance_data["tags"])
        assert len(list(instance.volumes.all())) == 1
        return instance

    return _mock_instance


@pytest.fixture()
def mock_instance_with_volume(mock_instance):
    def _mock_instance_with_volume():
        instance = mock_instance()
        ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
        volume = ec2.create_volume(Size=1, AvailabilityZone=DEFAULT_REGION)
        volume.create_tags(Tags=[{'Key': 'Name', 'Value': 'ethermint_volume'}])
        volume.attach_to_instance(InstanceId=instance.id, Device="/device")
        return instance

    return _mock_instance_with_volume
