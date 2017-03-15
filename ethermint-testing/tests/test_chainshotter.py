import boto3
import mock
import pytest
from botocore.exceptions import ClientError
from mock import MagicMock

from chainmaker import RegionInstancePair
from chainshotter import Chainshotter
from settings import DEFAULT_REGION, DEFAULT_DEVICE
from utils import get_shh_key_file

ETHERMINT_P2P_PORT = 46656


@pytest.fixture()
def chainshotter(mockossystem, mocksubprocess):
    return Chainshotter()


@pytest.fixture()
def prepare_chainshot(chainmaker, chainshotter, mockregions):

    instances = chainmaker.create_ethermint_network(mockregions, "HEAD", "master_pub_key")
    return chainshotter.chainshot("Test", instances)


@pytest.mark.parametrize('regionscount', [2])
def test_chainshot_halts_restarts(chainshotter, mocksubprocess, mockregions, chainmaker):
    # 2 instances to check if halt and start are in right order
    [instance1, instance2] = chainmaker.create_ethermint_network(mockregions, "HEAD", "master_pub_key")
    mocksubprocess.reset_mock()

    chainshotter.chainshot("Test", [instance1, instance2])

    args_list = mocksubprocess.call_args_list
    assert len(args_list) == 4

    assert args_list[0:2] == [mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                        "'bash -s' < shell_scripts/halt_ethermint.sh".format(
        get_shh_key_file(instance.key_name),
        instance.public_ip_address), shell=True) for instance in [instance1, instance2]]

    assert args_list[2] == mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                     "'bash -s' < shell_scripts/run_ethermint.sh".format(
        get_shh_key_file(instance1.key_name),
        instance1.public_ip_address), shell=True)

    assert args_list[3] == mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                     "'bash -s' < shell_scripts/run_ethermint.sh {2}:{3}".format(
        get_shh_key_file(instance2.key_name),
        instance2.public_ip_address,
        instance1.public_ip_address,
        ETHERMINT_P2P_PORT), shell=True)


def test_chainshot_creates_snapshots(chainshotter, chainmaker, mockregions):
    instances = chainmaker.create_ethermint_network(mockregions, "HEAD", "master_pub_key")
    chainshotter.chainshot("Test", instances)
    total_snapshots = 0
    for region in set(mockregions):
        ec2_client = boto3.client('ec2', region_name=region)
        total_snapshots += len(ec2_client.describe_snapshots(Filters=[{'Name': 'description', 'Values': ['ethermint-backup']}]))
    assert total_snapshots == len(instances)


def test_chainshot_return_data(chainshotter, chainmaker, mockregions, mockami):
    instances = chainmaker.create_ethermint_network(mockregions, "HEAD", "master_pub_key")
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

        assert data["instance"]["ami"] == mockami
        # assert data["instance"]["tags"] == mock_instance_data["tags"]
        # assert data["instance"]["key_name"] == mock_instance_data["key_name"]
        # assert data["instance"]["security_groups"][0] == mock_instance_data["security_group_name"]
        # TODO rest of fields: instnace: vpc_id, availablility_zone, id; snapshot: from, to


def test_invalid_chainshots(chainshotter, monkeypatch):
    # patch to don't have complains about the instance missing in aws
    monkeypatch.setattr('chainmaker.RegionInstancePair.instance', MagicMock())
    instances = [RegionInstancePair(DEFAULT_REGION, 'no-instance')]
    # volumes filter returns empty (no ethermint_volume)
    with pytest.raises(IndexError):
        chainshotter.chainshot("Test", instances)

    # UnauthorizedOperation when creating a snapshot - how to simulate?
    pass


def test_chainshot_cleanup(chainshotter, mockossystem):
    pass


def test_starting_instances_on_thaw(chainshotter, prepare_chainshot, monkeypatch):
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


@pytest.mark.parametrize('regionscount', [2])
def test_attaching_ebs_snapshots_on_thaw(chainshotter, prepare_chainshot):
    chainshot = prepare_chainshot
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


@pytest.mark.parametrize('regionscount', [2])
def test_mounting_ebs_and_running_on_thaw(chainshotter, mocksubprocess, prepare_chainshot):
    # For now testing if the ssh command is correct
    chainshot = prepare_chainshot
    mocksubprocess.reset_mock()
    [instance] = chainshotter.thaw(chainshot)[:1]

    args_list = mocksubprocess.call_args_list
    assert len(args_list) == 4

    assert args_list[0] == mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                     "'bash -s' < shell_scripts/mount_snapshot.sh".format(
        get_shh_key_file(instance.key_name),
        instance.public_ip_address), shell=True)

    assert args_list[2] == mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                     "'bash -s' < shell_scripts/run_ethermint.sh".format(
        get_shh_key_file(instance.key_name),
        instance.public_ip_address), shell=True)


def test_starting_ethermint_on_thaw(chainshotter):
    # How?
    pass


@pytest.mark.parametrize('regionscount', [2])
def test_invalid_thaws(chainshotter, prepare_chainshot, mockregions):
    # InvalidSnapshot
    chainshot = prepare_chainshot
    ec2_client = boto3.client('ec2', region_name=mockregions[0])
    ec2_client.delete_snapshot(SnapshotId=chainshot["instances"][0]["snapshot"]["id"])
    with pytest.raises(ClientError):
        chainshotter.thaw(chainshot)

    # What else?
    pass
