import os
from datetime import datetime

import boto3
import pytest
from chainshotter import Chainshotter
from mock import MagicMock
from moto import mock_ec2
from settings import DEFAULT_REGION, DEFAULT_INSTANCE_TYPE
from utils import to_canonical_region_name, get_shh_key_file


@pytest.fixture()
def mockossystem():
    return MagicMock(os.system)


@pytest.fixture()
def chainshotter(monkeypatch, mockossystem):
    monkeypatch.setattr(os, 'system', mockossystem)
    monkeypatch.setattr(os.path, 'exists', lambda path: True)
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
def prepare_chainshot():
    def _prepare_chainshot():
        ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
        volume = ec2.create_volume(Size=1, AvailabilityZone=DEFAULT_REGION)
        snapshot = ec2.create_snapshot(VolumeId=volume.id, Description='ethermint-backup')
        return {
            'instances':
                [
                    {
                        'instance': {'ami': 'imageID', 'tags': [{u'Value': 'testinstance', u'Key': 'Name'}],
                                     'key_name': 'Key', 'region': 'us-east-1a', 'vpc_id': None, 'id': 'i-47d03277',
                                     'security_groups': ['securitygroup']},
                        'snapshot': {'to': snapshot.start_time.isoformat(), 'from': '2017-03-02T10:25:49+00:00',
                                     'id': snapshot.id}}],
            'chainshot_name': 'Test'
        }
    return _prepare_chainshot


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
def test_starting_instances_and_attaching_ebs_snapshots_on_thaw(chainshotter, prepare_chainshot, mock_instance):
    chainshot = prepare_chainshot()
    chainshotter.chain_maker.from_json = MagicMock(return_value=mock_instance())
    instances = chainshotter.thaw(chainshot)

    assert len(instances) == 1

    chainshotter.chain_maker.from_json.assert_called_once_with(chainshot["instances"][0]["instance"])

    assert len(list(instances[0].volumes.filter(Filters=
    [
        {'Name': 'snapshot-id', 'Values': [chainshot["instances"][0]["snapshot"]["id"]]}
    ]))) == 1


@mock_ec2
def test_mounting_ebs_on_thaw(chainshotter, prepare_chainshot, mock_instance, mockossystem):
    # mount has to be done manually since the boto3 interface does not allow to do this
    # For now testing if the ssh command is correct
    chainshot = prepare_chainshot()
    instance = mock_instance()
    chainshotter.chain_maker.from_json = MagicMock(return_value=instance)
    chainshotter.thaw(chainshot)

    mockossystem.assert_called_once_with("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                         "'bash -s' < mount_snapshot.sh".format(get_shh_key_file(instance.key_name),
                                                                                instance.public_ip_address))


@mock_ec2
def test_starting_ethermint_on_thaw(chainshotter):
    # How?
    pass


@mock_ec2
def test_invalid_thaws(chainshotter):
    # InvalidSnapshot
    pass
