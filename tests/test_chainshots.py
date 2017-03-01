import os

import pytest
import boto3
import boto3.resources.base
from mock import MagicMock

import chainmaker
from chainshotter import Chainshotter


@pytest.fixture()
def mockresource():
    return MagicMock(boto3.resources.base.ServiceResource)


@pytest.fixture()
def mockchainmaker():
    return MagicMock(chainmaker.Chainmaker)


@pytest.fixture()
def mockossystem():
    return MagicMock(os.system)


@pytest.fixture()
def chainshotter(monkeypatch, mockresource, mockchainmaker, mockossystem):
    monkeypatch.setattr(boto3, 'resource', mockresource)
    monkeypatch.setattr(os, 'system', mockossystem)
    monkeypatch.setattr(os.path, 'exists', lambda path: True)
    chainshotter = Chainshotter()
    chainshotter.chain_maker = mockchainmaker
    return chainshotter


@pytest.fixture()
def chainshot_data():
    return {
        u'instances':
            [
                {
                    u'instance': {
                        u'ami': u'ami-06875e10',
                        u'tags': [{u'Key': u'Name',
                                   u'Value': u'test-ethermint-ami-06875e100'}],
                        u'key_name': u'salt-instance1488356742',
                        u'region': u'us-east-1b',
                        u'security_groups': [
                            u'ethermint-security_group-1']},
                    u'snapshot':
                        {
                            u'id': u'snap-0ddf1f9ce14398e63'
                        }
                },
                {
                    u'instance': {
                        u'ami': u'ami-06875e10',
                        u'tags': [{u'Key': u'Name',
                                   u'Value': u'test-ethermint-ami-06875e101'}],
                        u'key_name': u'salt-instance1488356813',
                        u'region': u'us-east-1b',
                        u'security_groups': [
                            u'ethermint-security_group-1']},
                    u'snapshot': {
                        u'id': u'snap-0837e5bec807bdccf'
                    }
                }
            ],
        u'chainshot_name': u'my_first_test_snapshot'
    }


def test_starting_and_mounting_ebs_snapshots_on_thaw(chainshotter, mockresource, mockchainmaker, mockossystem,
                                                     chainshot_data):
    chainshotter.thaw(chainshot_data)

    for inst in chainshot_data["instances"]:
        mockchainmaker.from_json.assert_any_call(inst["instance"])
        mockresource.create_volume.assert_any_call(inst["snapshot"]["id"],
                                                           inst["instance"]["region"])
        # check attach volume

    # more detailed check
    mockossystem.assert_has_calls(len(chainshot_data["instances"]))


@pytest.fixture()
def mockinstnace():
    def _mockinstance(vol_id):
        instance = MagicMock()
        mockvolume = MagicMock()
        mockvolume.id = MagicMock(return_value=vol_id)
        instance.volumes.filter = MagicMock(return_value=[mockvolume])
        return instance
    return _mockinstance


def test_ebs_snapshot(chainshotter, mockresource, mockinstnace):
    vol_id_1, vol_id_2 = "VolumeID1", "VolumeID2"
    chainshotter.chainshot("", [mockinstnace(vol_id_1), mockinstnace(vol_id_2)])

    # check if correct aws actions taken by boto3 mock
    mockresource.create_snapshot.assert_any_call(vol_id_1)
    mockresource.create_snapshot.assert_any_call(vol_id_2)

# FIXME: ideas about other tests

# def test_chainshot_data(chainshotter):
#     chainshotter.chainshot("name1", ["instance1", "instance2"])
#
#     # check if aws' and our data compiled correctly in resulting chainshot data
#
#
# def test_returning_instances_on_thaw(chainshotter):
#     instances = chainshotter.thaw(chainshot, ami)
#
#     # check if instances holds something sensible, to be referenced by subsequent test
#
#
# def test_starting_ethermint_on_thaw(chainshotter):
#     chainshotter.thaw(chainshot, ami)
#
#     # check if salt got the right instructions
#
#
# def test_invalid_chainshots(chainshotter):
#     pass
#
#
# def test_invalid_thaws(chainshotter):
#     pass
