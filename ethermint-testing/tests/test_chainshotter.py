import os

import boto3
import mock
import pytest
from botocore.exceptions import ClientError
from mock import MagicMock

from chainmaker import Chainmaker
from chainshotter import Chainshotter
from settings import DEFAULT_REGION, DEFAULT_DEVICE
from utils import get_shh_key_file

ETHERMINT_P2P_PORT = 46656


@pytest.fixture()
def chainshotter(monkeypatch, mockossystem):
    monkeypatch.setattr(os, 'system', mockossystem)
    monkeypatch.setattr(os.path, 'exists', lambda path: True)
    return Chainshotter()


@pytest.fixture()
def prepare_chainshot(moto):
    def _prepare_chainshot(regions):
        instances_list = []
        for region in regions:
            ec2 = boto3.resource('ec2', region_name=region)
            volume = ec2.create_volume(Size=1, AvailabilityZone=region)
            snapshot = ec2.create_snapshot(VolumeId=volume.id, Description='ethermint-backup')
            instances_list.append({
                        'instance': {'ami': 'imageID', 'tags': [{u'Value': 'testinstance', u'Key': 'Name'}],
                                     'key_name': 'Key', 'region': region, 'availablility_zone': region,
                                     'vpc_id': None, 'id': 'i-47d03277', 'security_groups': ['securitygroup']},
                        'snapshot': {'to': snapshot.start_time.isoformat(), 'from': '2017-03-02T10:25:49+00:00',
                                     'id': snapshot.id}})
        return {
            'instances': instances_list,
            'chainshot_name': 'Test'
        }
    return _prepare_chainshot


def test_chainshot_halts_restarts(chainshotter, mock_instance_with_volume, mockossystem):
    # 2 instances to check if halt and start are in right order
    instance1 = mock_instance_with_volume()
    instance2 = mock_instance_with_volume()
    chainshotter.chainshot("Test", {instance1.id: DEFAULT_REGION, instance2.id: DEFAULT_REGION})

    args_list = mockossystem.call_args_list
    assert len(args_list) == 4

    assert args_list[0:2] == [mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                        "'bash -s' < shell_scripts/halt_ethermint.sh".format(
        get_shh_key_file(instance.key_name),
        instance.public_ip_address)) for instance in [instance1, instance2]]

    assert args_list[2] == mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                     "'bash -s' < shell_scripts/run_ethermint.sh".format(
        get_shh_key_file(instance1.key_name),
        instance1.public_ip_address))

    assert args_list[3] == mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                     "'bash -s' < shell_scripts/run_ethermint.sh {2}:{3}".format(
        get_shh_key_file(instance2.key_name),
        instance2.public_ip_address,
        instance1.public_ip_address,
        ETHERMINT_P2P_PORT))


def test_chainshot_creates_snapshots(chainshotter, mock_instances_with_volumes, mockregions):
    instances = mock_instances_with_volumes(mockregions)
    chainshotter.chainshot("Test", instances)
    total_snapshots = 0
    for region in set(mockregions):
        ec2_client = boto3.client('ec2', region_name=region)
        total_snapshots += len(ec2_client.describe_snapshots(Filters=[{'Name': 'description', 'Values': ['ethermint-backup']}]))
    assert total_snapshots == len(instances)


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


def test_invalid_chainshots(chainshotter, mock_instance):
    # volumes filter returns empty (no ethermint_volume)
    instances = {mock_instance().id: DEFAULT_REGION}
    with pytest.raises(IndexError):
        chainshotter.chainshot("Test", instances)

    # UnauthorizedOperation when creating a snapshot - how to simulate?
    pass


def test_chainshot_cleanup(chainshotter, mock_instance_with_volume, mockossystem):
    pass


def test_starting_instances_on_thaw(chainshotter, prepare_chainshot, monkeypatch, mock_instance):
    # TODO
    pass
    # instances_count = 4
    # chainshot = prepare_chainshot([DEFAULT_REGION] * instances_count)
    # monkeypatch.setattr(Chainmaker, 'create_ec2s_from_json', MagicMock(return_value=[mock_instance()]))
    # instances = chainshotter.thaw(chainshot)
    #
    # assert len(instances) == len(chainshot["instances"])
    #
    # assert Chainmaker.create_ec2s_from_json.call_count == instances_count
    #
    # for c in chainshot["instances"]:
    #     Chainmaker.create_ec2s_from_json.assert_has_calls([c["instance"]])


def test_attaching_ebs_snapshots_on_thaw(chainshotter, prepare_chainshot, mock_instance,
                                                                monkeypatch, mockregions):
    chainshot = prepare_chainshot(mockregions)
    monkeypatch.setattr(Chainmaker, 'create_ec2s_from_json', lambda self, config: [mock_instance(config[0]["region"])])
    instances = chainshotter.thaw(chainshot)

    snapshot_ids = [inst["snapshot"]["id"] for inst in chainshot["instances"]]
    for instance in instances:
        volumes = list(instance.volumes.filter(Filters=
        [
            {'Name': 'snapshot-id', 'Values': snapshot_ids}
        ]))
        assert len(volumes) == 1
        assert volumes[0].attachments[0]["Device"] == DEFAULT_DEVICE
        for bdm in instance.block_device_mappings:
            if bdm["Ebs"]["VolumeId"] == volumes[0].id:
                assert bdm["DeviceName"] == DEFAULT_DEVICE


def test_mounting_ebs_and_running_on_thaw(chainshotter, prepare_chainshot, mock_instance, mockossystem, monkeypatch,
                                          mockregions):
    # mount has to be done manually since the boto3 interface does not allow to do this
    # For now testing if the ssh command is correct
    chainshot = prepare_chainshot([DEFAULT_REGION])
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


def test_starting_ethermint_on_thaw(chainshotter):
    # How?
    pass


def test_invalid_thaws(chainshotter, prepare_chainshot):
    # InvalidSnapshot
    chainshot = prepare_chainshot([DEFAULT_REGION])
    ec2_client = boto3.client('ec2', region_name=DEFAULT_REGION)
    ec2_client.delete_snapshot(SnapshotId=chainshot["instances"][0]["snapshot"]["id"])
    with pytest.raises(ClientError):
        chainshotter.thaw(chainshot)

    # What else?
    pass
