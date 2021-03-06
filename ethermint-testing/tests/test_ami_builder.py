import packer
import pytest
from mock import MagicMock

from amibuilder import AMIBuilder


@pytest.fixture()
def mockpacker():
    return MagicMock(packer.Packer)


@pytest.fixture()
def amibuilder(monkeypatch, mockpacker, tmp_files_dir, mock_aws_credentials):
    monkeypatch.setattr(packer, 'Packer', mockpacker)
    amibuilder = AMIBuilder("master priv key contents", tmp_files_dir)
    sample_output = """
        amazon-ebs: Setting up python-msgpack (0.3.0-1ubuntu3) ...
        amazon-ebs: Setting up salt-common (2015.5.3+ds-1trusty1) ...
        amazon-ebs: Processing triggers for ufw (0.34~rc-0ubuntu2) ...
        amazon-ebs: Setting up salt-ssh (2015.5.3+ds-1trusty1) ...
    ==> amazon-ebs: Stopping the source instance...
    ==> amazon-ebs: Waiting for the instance to stop...
    ==> amazon-ebs: Creating the AMI: test_salt_ssh_minion_ami
        amazon-ebs: AMI: ami-10d50c06
        """

    class MyBuildResult:
        def __init__(self, output):
            self.stdout = output

    amibuilder.packer.build = MagicMock(return_value=MyBuildResult(sample_output))
    return amibuilder


def test_ami_creation(amibuilder):
    ami_name = "test_ami"
    amibuilder.create_ami("abcdabcdabcdabcdabcdabcdabcdabcd", ami_name)
    amibuilder.packer.validate.assert_called_once()
    amibuilder.packer.build.assert_called_once()
