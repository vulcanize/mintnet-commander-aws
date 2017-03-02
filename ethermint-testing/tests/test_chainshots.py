import os

import boto3
import boto3.resources.base
import chainmaker
import pytest
from chainshotter import Chainshotter
from mock import MagicMock


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

# def test_invalid_thaws(chainshotter):
#     pass
