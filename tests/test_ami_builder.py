import packer
import pytest
from mock import MagicMock

from amibuilder import AMIBuilder


@pytest.fixture()
def mockpacker():
    return MagicMock(packer.Packer)


@pytest.fixture()
def amibuilder(monkeypatch, mockpacker):
    monkeypatch.setattr(packer, 'Packer', mockpacker)

    sample_output = """

    """

    mockpacker.build = MagicMock(return_value=sample_output)
    return AMIBuilder()


def test_ami_creation(amibuilder):
    base_config = {"builders": []}
    ami_name = "test_ami"
    packer_file_name = "packer-file"
    amibuilder.create_ami(base_config, ami_name, packer_file_name)
    mockpacker.validate.assert_called_once()
    mockpacker.build.assert_called_once()
