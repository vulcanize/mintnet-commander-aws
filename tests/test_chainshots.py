import pytest
import boto3
import boto3.resources.base
from mock import MagicMock

from chainshotter import Chainshotter


@pytest.fixture()
def mockresource():
    return MagicMock(boto3.resources.base.ServiceResource)


@pytest.fixture()
def chainshotter(monkeypatch, mockresource):
    monkeypatch.settatr(boto3, 'resource', mockresource)
    return Chainshotter()


def test_starting_and_mounting_ebs_snapshots_on_thaw(chainshotter, mockresource):
    # monkeypatch boto3.resource to return mock

    # NOTE: I'm starting to see that .thaw should probably call a specific version of .create first, off a specific ami
    # it might even be easier this way. After .create exists of course
    chainshotter.thaw(chainshot, ami)

    # test whether correct aws actions taken by boto3 mock - should start instance and mount ebs

# FIXME: ideas about other tests
#
# def test_ebs_snapshots(chainshotter):
#     # monkeypatch boto3.resource to return mock
#     chainshotter.chainshot("", ["instance1", "instance2"])
#
#     # check if correct aws actions taken by boto3 mock
#
#
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
