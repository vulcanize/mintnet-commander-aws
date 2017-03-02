import pytest
from moto import mock_ec2

from chainmaker import Chainmaker


@pytest.fixture()
def chainmaker():
    return Chainmaker()


@mock_ec2
def test_security_group_creation():
    pass


@mock_ec2
def test_adding_volume_to_instance():
    pass


@mock_ec2
def test_adding_volume_failures():
    pass


@mock_ec2
def test_creating_from_json():
    pass

