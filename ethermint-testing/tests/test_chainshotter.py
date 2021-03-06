from time import sleep
import datetime

import pytz
import boto3
import dateutil.parser
import mock
import pytest
from botocore.exceptions import ClientError
from mock import MagicMock

from chain import Chain
from chainmanager import RegionInstancePair
from chainshotter import Chainshotter
from settings import DEFAULT_REGION, DEFAULT_DEVICE
from utils import get_shh_key_file

ETHERMINT_P2P_PORT = 46656


@pytest.fixture()
def chainshotter(mockossystem, mocksubprocess):
    return Chainshotter()


@pytest.fixture()
def prepare_chainshot(chainmanager, chainshotter, mockregions, ethermint_version):

    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version)
    return chainshotter.chainshot("Test", chain)


@pytest.mark.parametrize('regionscount', [2])
def test_chainshot_halts_restarts(chainshotter, mocksubprocess, mockregions, chainmanager, ethermint_version):
    # 2 instances to check if halt and start are in right order
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version)
    mocksubprocess.reset_mock()

    [instance1, instance2] = chain.instances

    chainshotter.chainshot("Test", chain)

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


def test_chainshot_creates_snapshots(chainshotter, chainmanager, mockregions, ethermint_version):
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version)
    chainshotter.chainshot("Test", chain)
    total_snapshots = 0
    for region in set(mockregions):
        ec2_client = boto3.client('ec2', region_name=region)
        all_snaps = ec2_client.describe_snapshots(Filters=[{'Name': 'description', 'Values': ['ethermint-backup']}])
        all_snaps = [snapshot["SnapshotId"] for snapshot in all_snaps["Snapshots"]]
        total_snapshots += len(all_snaps)
        assert len(all_snaps) == mockregions.count(region)
    assert total_snapshots == len(chain.instances)


def test_chainshot_return_data(chainshotter, chainmanager, mockregions, mockami, ethermint_version):
    time1 = datetime.datetime.now(tz=pytz.UTC).replace(microsecond=0)
    sleep(1)  # sleeping to put differentiate times from aws with second resolution and make test deterministic
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version)
    sleep(1)
    time2 = datetime.datetime.now(tz=pytz.UTC).replace(microsecond=0)
    sleep(1)
    chainshot_data = chainshotter.chainshot("Test", chain)
    sleep(1)
    time3 = datetime.datetime.now(tz=pytz.UTC).replace(microsecond=0)

    snapshots_in_regions = {}
    for region in set(mockregions):
        ec2_client = boto3.client('ec2', region_name=region)
        all_snaps = ec2_client.describe_snapshots(Filters=[{'Name': 'description', 'Values': ['ethermint-backup']}])
        all_snaps = [snapshot["SnapshotId"] for snapshot in all_snaps["Snapshots"]]
        snapshots_in_regions[region] = all_snaps

    for i, data in enumerate(chainshot_data["instances"]):
        region = data["instance"]["region"]

        assert region in mockregions
        del mockregions[mockregions.index(region)]  # make sure there are exactly as many as should be

        assert data["snapshot"]["id"] in snapshots_in_regions[region]

        assert data["instance"]["ami"] == mockami
        assert data["instance"]["tags"] == chain.instances[i].tags
        assert data["instance"]["key_name"] == chain.instances[i].key_name
        assert data["instance"]["security_groups"][0] == chain.instances[i].security_groups[0]['GroupName']

        snapshot_from = dateutil.parser.parse(data["snapshot"]["from"])
        snapshot_to = dateutil.parser.parse(data["snapshot"]["to"])

        assert time1 < snapshot_from < time2
        assert time2 < snapshot_to < time3


def test_invalid_chainshots(chainshotter, monkeypatch, moto):
    # patch to not have complains about the instance missing in aws
    monkeypatch.setattr('chainmanager.RegionInstancePair.instance', MagicMock())
    chain = Chain([RegionInstancePair(DEFAULT_REGION, 'no-instance')])
    # volumes filter returns empty (no ethermint_volume)
    with pytest.raises(IndexError):
        chainshotter.chainshot("Test", chain)

    # UnauthorizedOperation when creating a snapshot - how to simulate?
    pass


@pytest.mark.parametrize('regionscount', [2])
def test_attaching_ebs_snapshots_on_thaw(chainshotter, prepare_chainshot):
    chainshot = prepare_chainshot
    chain = chainshotter.thaw(chainshot)

    snapshot_ids = [inst["snapshot"]["id"] for inst in chainshot["instances"]]
    for instance in chain.instances:
        volumes = list(instance.volumes.filter(Filters=[
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
    chain = chainshotter.thaw(chainshot)
    instance = chain.instances[0]

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


@pytest.mark.parametrize('regionscount', [2])
def test_thaw_printable(chainshotter, prepare_chainshot, capsys):
    chainshot = prepare_chainshot
    chain = chainshotter.thaw(chainshot)

    print(chain)

    out, err = capsys.readouterr()
    assert err == ""

    for i, line in enumerate(out.split('\n')):
        if line == '':
            continue
        region, instance_id = line.split(':')
        assert region == chain.instances[i].region_name
        assert instance_id == chain.instances[i].id
