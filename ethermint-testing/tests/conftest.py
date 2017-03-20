import subprocess
import shutil
from os.path import join, dirname
import os

import boto3
import pytest
from mock import MagicMock
from moto import mock_ec2

from chainmanager import Chainmanager
import fill_validators
from amibuilder import AMIBuilder

SECURITY_GROUP_NAME = "securitygroup"
ETHERMINT_VERSION = "01230123012301230123012301230123"


@pytest.fixture()
def mockami():
    return "ami-90b01686"


@pytest.fixture()
def moto():
    mock_ec2().start()
    yield None
    mock_ec2().stop()


@pytest.fixture()
def mockossystem(monkeypatch):
    mock = MagicMock(os.system, return_value=0)
    monkeypatch.setattr(os, 'system', mock)
    return mock


@pytest.fixture()
def ethermint_version():
    return ETHERMINT_VERSION


@pytest.fixture()
def mocksubprocess(monkeypatch, ethermint_version):
    def _responses(*args, **kwargs):
        if "get_ethermint_version" in args[0]:
            return ethermint_version
        else:
            return ""

    mock = MagicMock(subprocess.check_output, side_effect=_responses)
    monkeypatch.setattr(subprocess, 'check_output', mock)
    return mock


@pytest.fixture()
def mock_security_group(moto, mock_instance_data):
    def ret(region):
        ec2 = boto3.resource('ec2', region_name=region)
        security_group_name = mock_instance_data["security_group_name"]
        groups = list(ec2.security_groups.filter(GroupNames=[security_group_name]))
        if len(groups) > 0:
            g = groups[0]
        else:
            g = ec2.create_security_group(GroupName=security_group_name, Description="test group")
        return g
    return ret


@pytest.fixture()
def mock_aws_credentials(monkeypatch, tmpdir):
    credentials_file = tmpdir.mkdir("awsfiles").join("credentials")
    credentials_file.write("""
[default]
aws_access_key_id = AAAAAAAAAAAAAAAAAAAA
aws_secret_access_key = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
    """)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(credentials_file))


@pytest.fixture()
def tmp_files_dir(tmpdir, monkeypatch):
    dir = str(tmpdir.mkdir("files"))
    monkeypatch.setattr('utils.DEFAULT_FILES_LOCATION', dir)
    monkeypatch.setattr('chainmanager.DEFAULT_FILES_LOCATION', dir)
    return dir


@pytest.fixture()
def fake_ethermint_files(tmp_files_dir, monkeypatch):
    """
    Ensures that fake ethermint files are generated without calls to os.system
    """
    testsdir = os.path.dirname(os.path.realpath(__file__))
    dest = join(tmp_files_dir, "ethermint", "priv_validator.json.{}")
    if not os.path.exists(dirname(dest)):
        os.makedirs(dirname(dest))
    dest_datadir = join(tmp_files_dir, "ethermint", "data")
    if not os.path.exists(dest_datadir):
        os.makedirs(dest_datadir)

    def _mock_call_gen_validator(path):
        shutil.copyfile(os.path.join(testsdir, "priv_validator.json.in"), path)

    monkeypatch.setattr(fill_validators, 'call_gen_validator', MagicMock(side_effect=_mock_call_gen_validator))

    def _mock_call_init(dir):
        shutil.copy(os.path.join(testsdir, "genesis.json"), dir)

    monkeypatch.setattr(fill_validators, 'call_init', MagicMock(side_effect=_mock_call_init))

    return None


@pytest.fixture()
def regionscount():
    return 6


@pytest.fixture()
def mockregions(regionscount):
    return ["ap-northeast-1", "us-west-1", "ap-northeast-1",
            "ap-northeast-1", "eu-central-1", "us-west-1"][:regionscount]


@pytest.fixture()
def mockamibuilder(mockami, monkeypatch):
    mock = MagicMock(AMIBuilder)
    mock.create_ami.return_value = mockami

    monkeypatch.setattr('chainmanager.AMIBuilder', MagicMock(return_value=mock))
    return mock


@pytest.fixture()
def chainmanager(monkeypatch, mockossystem, mocksubprocess,
                 mockamibuilder, tmp_files_dir, fake_ethermint_files, moto):
    # generic "all mocked out" instance
    return Chainmanager()
