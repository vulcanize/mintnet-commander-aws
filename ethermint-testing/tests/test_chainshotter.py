import os

import boto3
import pytest
from botocore.exceptions import ClientError
from mock import MagicMock
from moto import mock_ec2

from chainmaker import Chainmaker
from chainshotter import Chainshotter
from settings import DEFAULT_REGION, DEFAULT_DEVICE
from utils import to_canonical_region_name, get_shh_key_file


@pytest.fixture()
def chainshotter(monkeypatch, mockossystem):
    monkeypatch.setattr(os, 'system', mockossystem)
    monkeypatch.setattr(os.path, 'exists', lambda path: True)
    return Chainshotter()


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
def test_starting_instances_and_attaching_ebs_snapshots_on_thaw(chainshotter, prepare_chainshot, mock_instance,
                                                                monkeypatch):
    chainshot = prepare_chainshot()
    monkeypatch.setattr(Chainmaker, 'create_ec2s_from_json', MagicMock(return_value=[mock_instance()]))
    instances = chainshotter.thaw(chainshot)

    assert len(instances) == 1

    Chainmaker.create_ec2s_from_json.assert_called_once_with([chainshot["instances"][0]["instance"]])

    assert len(list(instances[0].volumes.filter(Filters=
    [
        {'Name': 'snapshot-id', 'Values': [chainshot["instances"][0]["snapshot"]["id"]]}
    ]))) == 1

    assert instances[0].block_device_mappings[1]["DeviceName"] == DEFAULT_DEVICE


@mock_ec2
def test_mounting_ebs_on_thaw(chainshotter, prepare_chainshot, mock_instance, mockossystem, monkeypatch):
    # mount has to be done manually since the boto3 interface does not allow to do this
    # For now testing if the ssh command is correct
    chainshot = prepare_chainshot()
    instance = mock_instance()
    monkeypatch.setattr(Chainmaker, 'create_ec2s_from_json', MagicMock(return_value=[instance]))
    chainshotter.thaw(chainshot)

    mockossystem.assert_called_once_with("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                         "'bash -s' < shell_scripts/mount_snapshot.sh".format(
        get_shh_key_file(instance.key_name),
        instance.public_ip_address))


@mock_ec2
def test_starting_ethermint_on_thaw(chainshotter):
    # How?
    pass


@mock_ec2
def test_invalid_thaws(chainshotter, prepare_chainshot):
    # InvalidSnapshot
    chainshot = prepare_chainshot()
    ec2_client = boto3.client('ec2', region_name=DEFAULT_REGION)
    ec2_client.delete_snapshot(SnapshotId=chainshot["instances"][0]["snapshot"]["id"])
    with pytest.raises(ClientError):
        chainshotter.thaw(chainshot)

    # What else?
    pass
