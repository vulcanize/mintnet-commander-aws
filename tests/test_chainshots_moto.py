from datetime import datetime

import boto3
import pytest
from moto import mock_ec2

from chainshotter import Chainshotter
from settings import DEFAULT_REGION, DEFAULT_INSTANCE_TYPE
from utils import to_canonical_region_name


@pytest.fixture()
def chainshotter():
    return Chainshotter()


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


@mock_ec2
def test_chainshot_creates_snapshots(chainshotter, mock_instance_with_volume):
    instances = [mock_instance_with_volume()]
    chainshotter.chainshot("Test", instances)
    ec2_client = boto3.client('ec2', region_name=DEFAULT_REGION)
    all_snaps = ec2_client.describe_snapshots(Filters=[{'Name': 'description', 'Values': ['ethermint-backup']}])
    assert len(all_snaps) - 1 == len(instances)  # not counting the default Created by CreateImage snapshot


@mock_ec2
def test_chainshot_return_data(chainshotter, mock_instance_with_volume, mock_instance_data):
    chainshot_data = chainshotter.chainshot("Test", [mock_instance_with_volume()])
    ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
    ec2_client = boto3.client('ec2', region_name=DEFAULT_REGION)
    all_snaps = ec2_client.describe_snapshots(Filters=[{'Name': 'description', 'Values': ['ethermint-backup']}])
    all_snaps = [ec2.Snapshot(snapshot["SnapshotId"]) for snapshot in all_snaps["Snapshots"]]
    assert len(all_snaps) == 1
    snapshot = all_snaps[0]

    for data in chainshot_data["instances"]:
        assert data["snapshot"]["id"] == snapshot.id
        # assert data["snapshot"]["from"] == instance.launch_time.isoformtat()
        assert data["snapshot"]["to"] == snapshot.start_time.isoformat()

        # left: vpc_id, id
        assert to_canonical_region_name(data["instance"]["region"]) == DEFAULT_REGION
        assert data["instance"]["ami"] == mock_instance_data["image_id"]
        assert data["instance"]["tags"] == mock_instance_data["tags"]
        assert data["instance"]["key_name"] == mock_instance_data["key_name"]
        assert data["instance"]["security_groups"][0] == mock_instance_data["security_group_name"]


@mock_ec2
def test_invalid_chainshots(chainshotter, mock_instance):
    # volumes filter returns empty (no ethermint_volume)
    instance = mock_instance()
    with pytest.raises(IndexError):
        chainshotter.chainshot("Test", [instance])

    # UnauthorizedOperation when creating a snapshot - how to simulate?
    pass


@mock_ec2
def test_starting_and_mounting_ebs_snapshots_on_thaw(chainshotter):
    pass


@mock_ec2
def test_returning_instances_on_thaw(chainshotter):
    pass


@mock_ec2
def test_starting_ethermint_on_thaw(chainshotter):
    pass


@mock_ec2
def test_invalid_thaws(chainshotter):
    pass
