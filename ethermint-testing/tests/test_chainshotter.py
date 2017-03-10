import os

import boto3
import mock
import pytest
from botocore.exceptions import ClientError
from mock import MagicMock
from moto import mock_ec2

from chainmaker import Chainmaker
from chainshotter import Chainshotter
from settings import DEFAULT_REGION, DEFAULT_DEVICE
from utils import get_shh_key_file


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
                                     'key_name': 'Key', 'region': 'us-east-1', 'availablility_zone': 'us-east-1a',
                                     'vpc_id': None, 'id': 'i-47d03277', 'security_groups': ['securitygroup']},
                        'snapshot': {'to': snapshot.start_time.isoformat(), 'from': '2017-03-02T10:25:49+00:00',
                                     'id': snapshot.id}}],
            'chainshot_name': 'Test'
        }

    return _prepare_chainshot


@mock_ec2
def test_chainshot_creates_snapshots(chainshotter, mock_instances_with_volumes, mockregions):
    instances = mock_instances_with_volumes(mockregions)
    chainshotter.chainshot("Test", instances)
    total_snapshots = 0
    for region in set(mockregions):
        ec2_client = boto3.client('ec2', region_name=region)
        total_snapshots += len(ec2_client.describe_snapshots(Filters=[{'Name': 'description', 'Values': ['ethermint-backup']}]))
    assert total_snapshots == len(instances)


@mock_ec2
def test_chainshot_return_data(chainshotter, mock_instances_with_volumes, mockregions, mock_instance_data):
    instances = mock_instances_with_volumes(mockregions)
    chainshot_data = chainshotter.chainshot("Test", instances)

    snapshots_in_regions = {}
    for region in set(mockregions):
        ec2_client = boto3.client('ec2', region_name=region)
        all_snaps = ec2_client.describe_snapshots(Filters=[{'Name': 'description', 'Values': ['ethermint-backup']}])
        all_snaps = [snapshot["SnapshotId"] for snapshot in all_snaps["Snapshots"]]
        snapshots_in_regions[region] = all_snaps
        assert len(all_snaps) == mockregions.count(region)

    for i, data in enumerate(chainshot_data["instances"]):
        region = data["instance"]["region"]

        assert region in mockregions
        del mockregions[mockregions.index(region)]  # make sure there are exactly as many as should be

        assert data["snapshot"]["id"] in snapshots_in_regions[region]

        assert data["instance"]["ami"] == mock_instance_data["image_id"]
        assert data["instance"]["tags"] == mock_instance_data["tags"]
        assert data["instance"]["key_name"] == mock_instance_data["key_name"]
        assert data["instance"]["security_groups"][0] == mock_instance_data["security_group_name"]
        # TODO rest of fields: instnace: vpc_id, availablility_zone, id; snapshot: from, to


@mock_ec2
def test_invalid_chainshots(chainshotter, mock_instance):
    # volumes filter returns empty (no ethermint_volume)
    instances = {mock_instance().id: DEFAULT_REGION}
    with pytest.raises(IndexError):
        chainshotter.chainshot("Test", instances)

    # UnauthorizedOperation when creating a snapshot - how to simulate?
    pass


@mock_ec2
def test_chainshot_cleanup(chainshotter, mock_instance_with_volume, mockossystem):
    pass
    # instance = mock_instance_with_volume()
    # instances = {instance.id: DEFAULT_REGION}
    # chainshotter.chainshot("Test", instances, clean_up=True)
    #
    # mockossystem.assert_called_once_with("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
    #                                      "'bash -s' < shell_scripts/unmount_new_volume.sh".format(
    #     get_shh_key_file(instance.key_name),
    #     instance.public_ip_address))
    #
    # # TODO test detaching and deleting volume here
    #
    # assert instance.state["Name"] == 'terminated'


@mock_ec2
def test_starting_instances_and_attaching_ebs_snapshots_on_thaw(chainshotter, prepare_chainshot, mock_instance,
                                                                monkeypatch):
    chainshot = prepare_chainshot()
    monkeypatch.setattr(Chainmaker, 'create_ec2s_from_json', MagicMock(return_value=[mock_instance()]))
    instances = chainshotter.thaw(chainshot)

    assert len(instances) == 1

    Chainmaker.create_ec2s_from_json.assert_called_once_with([chainshot["instances"][0]["instance"]])

    volumes = list(instances[0].volumes.filter(Filters=
    [
        {'Name': 'snapshot-id', 'Values': [chainshot["instances"][0]["snapshot"]["id"]]}
    ]))
    assert len(volumes) == 1
    assert volumes[0].attachments[0]["Device"] == DEFAULT_DEVICE
    for bdm in instances[0].block_device_mappings:
        if bdm["Ebs"]["VolumeId"] == volumes[0].id:
            assert bdm["DeviceName"] == DEFAULT_DEVICE


@mock_ec2
def test_mounting_ebs_and_running_on_thaw(chainshotter, prepare_chainshot, mock_instance, mockossystem, monkeypatch):
    # mount has to be done manually since the boto3 interface does not allow to do this
    # For now testing if the ssh command is correct
    chainshot = prepare_chainshot()
    instance = mock_instance()
    monkeypatch.setattr(Chainmaker, 'create_ec2s_from_json', MagicMock(return_value=[instance]))
    mockossystem.reset_mock()
    chainshotter.thaw(chainshot)

    args_list = mockossystem.call_args_list
    assert len(args_list) == 2

    assert args_list[0] == mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                     "'bash -s' < shell_scripts/mount_snapshot.sh".format(
        get_shh_key_file(instance.key_name),
        instance.public_ip_address))

    assert args_list[1] == mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                     "'bash -s' < shell_scripts/run_ethermint.sh".format(
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
