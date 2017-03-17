import os

import boto3
import mock
import pytest
import yaml
from mock.mock import MagicMock

from chainmaker import Chainmaker, RegionInstancePair
from settings import DEFAULT_DEVICE, DEFAULT_PORTS
from utils import get_shh_key_file


@pytest.fixture()
def create_mock_amis(mockami, mockamibuilder):
    """
    Makes the mockamibuilder pretend to be building amis in regions
    """
    def _create(ethermint_version, ami_name, regions=None):
        for region in regions:
            ec2 = boto3.resource('ec2', region_name=region)
            ec2_client = boto3.client('ec2', region_name=region)
            instance = ec2.create_instances(ImageId=mockami, MinCount=1, MaxCount=1)[0]
            ami = ec2_client.create_image(InstanceId=instance.id, Name=ami_name)
            ec2.Image(ami["ImageId"]).create_tags(Tags=[{'Key': 'Ethermint', "Value": ethermint_version}])

        return mockami

    mockamibuilder.create_ami.side_effect = _create


def test_creating_ethermint_network(chainmaker, mockami, mockregions, ethermint_version):
    nodes = chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    distinct_regions = set(mockregions)
    instances_in_regions = {}
    for r in mockregions:
        instances_in_regions[r] = instances_in_regions.get(r, 0) + 1

    for region in distinct_regions:
        ec2 = boto3.resource('ec2', region_name=region)
        assert len(list(ec2.instances.all())) == instances_in_regions[region]

    # check if nodes have the correct AMI
    for node in nodes:
        assert node.image_id == mockami
        # TODO check if image has correct tags?


def test_creating_ethermint_network_failures(chainmaker):
    pass


def test_ethermint_network_security_group(chainmaker, mockregions, ethermint_version):
    # test if nodes in the network can talk to each other (are in the same security group)
    nodes = chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    for node in nodes:
        ec2 = boto3.resource('ec2', region_name=node.region_name)
        node_sec_groups = [group["GroupId"] for group in node.security_groups]
        assert len(node_sec_groups) == 1

        security_group_ports = [range(ip_perm["FromPort"], ip_perm["ToPort"] + 1)
                                for ip_perm in ec2.SecurityGroup(node_sec_groups[0]).ip_permissions]
        security_group_ports = [item for sublist in security_group_ports for item in sublist]  # flatten list of lists
        assert sorted(security_group_ports) == sorted(DEFAULT_PORTS)


def test_ethermint_network_creates_AMIs(chainmaker, mockregions, mockamibuilder, ethermint_version):
    compare_ami_name = "test_ethermint{}_ami-ssh".format(ethermint_version[:8])
    chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    distinct_regions = set(mockregions)
    for region in distinct_regions:
        mockamibuilder.create_ami.assert_any_call(ethermint_version, compare_ami_name, regions=[region])


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_uses_existing_AMIs_when_exist(chainmaker, mockregions, mockamibuilder, create_mock_amis,
                                                         ethermint_version):

    chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    mockamibuilder.create_ami.reset_mock()

    chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    mockamibuilder.create_ami.assert_not_called()

    chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key", no_ami_cache=True)
    mockamibuilder.create_ami.assert_called()


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_new_AMIs_for_ethermint_versions(chainmaker, mockregions, mockamibuilder, create_mock_amis,
                                                   ethermint_version, mocksubprocess):

    chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    mockamibuilder.create_ami.reset_mock()

    other_version = "otherohterotherohterotherohter"
    mocksubprocess.side_effect = lambda *args, **kwargs: other_version if "get_ethermint_version.sh" in args[0] else ''
    chainmaker.create_ethermint_network(mockregions, other_version, "master_pub_key")
    mockamibuilder.create_ami.assert_called()


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_find_AMI(chainmaker, mockregions, mockamibuilder, create_mock_amis, ethermint_version):

    chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    mockamibuilder.create_ami.reset_mock()

    new_region = "us-gov-west-1"
    mockregions += [new_region]

    chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    calls = mockamibuilder.create_ami.call_args_list
    assert len(calls) == 1
    assert calls[0][1]['regions'] == [new_region]


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_attaches_volumes(chainmaker, mockregions, ethermint_version):
    nodes = chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    for node in nodes:
        assert len(node.block_device_mappings) == 2  # the default drive and our additional drive
        found_our_volume = False
        for bdm in node.block_device_mappings:
            if bdm["DeviceName"] == DEFAULT_DEVICE:
                found_our_volume = True
                break
        assert found_our_volume


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_mounts_volumes(chainmaker, mockregions, mocksubprocess, ethermint_version):
    # mount has to be done manually since the boto3 interface does not allow to do this
    # for now, testing if ssh command is correct
    nodes = chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    for node in nodes:
        mocksubprocess.assert_any_call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                       "'bash -s' < shell_scripts/mount_new_volume.sh".format(
            get_shh_key_file(node.key_name), node.public_ip_address),
            shell=True)


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_update_roster(chainmaker, mockregions, mockossystem, ethermint_version):
    nodes = chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key", update_salt_roster=True)
    nodes_ips = [node.public_ip_address for node in nodes]

    filepath = None
    sh_command_start = "shell_scripts/copy_roster.sh"
    for c in mockossystem.mock_calls:
        first_arg = c[1][0]
        if first_arg.startswith(sh_command_start):
            filepath = first_arg[first_arg.find(sh_command_start) + len(sh_command_start):].strip()
            break
    assert filepath

    with open(filepath, "r") as f:
        contents = yaml.safe_load(f)

    for c in contents:
        assert contents[c]['host'] in nodes_ips


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_prepares_for_ethermint(chainmaker, mockregions, mocksubprocess, mockossystem, tmp_files_dir,
                                                  ethermint_version):
    nodes = chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    ethermint_files_location = os.path.join(tmp_files_dir, "ethermint")

    for i, node in enumerate(nodes):
        mocksubprocess.assert_any_call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                       "'bash -s' < shell_scripts/prepare_ethermint_env.sh".format(
            get_shh_key_file(node.key_name), node.public_ip_address),
            shell=True)

        # make sure files are copied: data folder and priv_validator file
        mockossystem.assert_any_call("scp -o StrictHostKeyChecking=no -C -i {} -r {} ubuntu@{}:/ethermint".format(
            get_shh_key_file(node.key_name), os.path.join(ethermint_files_location, "data"),
            node.public_ip_address))

        validator_path = os.path.join(ethermint_files_location, "priv_validator.json.{}".format(i + 1))
        mockossystem.assert_any_call(
            "scp -o StrictHostKeyChecking=no -C -i {} {} ubuntu@{}:/ethermint/data/priv_validator.json".format(
                get_shh_key_file(node.key_name), validator_path,
                node.public_ip_address))


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_runs_ethermint(chainmaker, mockregions, mocksubprocess,
                                          ethermint_version):
    nodes = chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    first = None
    for node in nodes:
        if first:
            mocksubprocess.assert_any_call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                           "'bash -s' < shell_scripts/run_ethermint.sh {2}".format(
                get_shh_key_file(node.key_name), node.public_ip_address, str(first.public_ip_address) + ":46656"),
                shell=True)
        else:
            mocksubprocess.assert_any_call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                           "'bash -s' < shell_scripts/run_ethermint.sh".format(
                get_shh_key_file(node.key_name), node.public_ip_address),
                shell=True)
            first = node


@pytest.mark.parametrize('regionscount', [2])
def test_isalive_commands(chainmaker, mocksubprocess, mockregions, ethermint_version):
    nodes = chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    mocksubprocess.reset_mock()
    mocksubprocess.side_effect = ["a", "b"]
    result = chainmaker.isalive(RegionInstancePair(mockregions[0], nodes[0].id))

    call_args = mocksubprocess.call_args_list
    assert len(call_args) == 2
    assert call_args == [
        mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                  "'bash -s' < shell_scripts/log_ethermint.sh".format(
            get_shh_key_file(nodes[0].key_name),
            nodes[0].public_ip_address),
            shell=True),
        mock.call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                  "'bash -s' < shell_scripts/log_ethermint.sh".format(
            get_shh_key_file(nodes[0].key_name),
            nodes[0].public_ip_address),
            shell=True),
    ]

    # make sure the returned value signals "alive"
    assert result


@pytest.mark.parametrize('regionscount', [2])
def test_isalive_dead(chainmaker, mocksubprocess, mockregions, ethermint_version):
    nodes = chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    mocksubprocess.side_effect = ["a", "a"]  # same output
    result = chainmaker.isalive(RegionInstancePair(mockregions[0], nodes[0].id))

    assert not result


@pytest.mark.parametrize('regionscount', [2])
@pytest.mark.parametrize("pathcheck", ["tendermint version", "ethermint -h", "packer version"])
def test_check_path(chainmaker, mockregions, mockossystem, pathcheck, ethermint_version):
    chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    mockossystem.assert_any_call(pathcheck)


def test_chainmaker_imports_keypairs(chainmaker, mockregions, ethermint_version):
    chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    keypairs = []
    for region in mockregions:
        ec2 = boto3.client('ec2', region_name=region)
        currentkeypairs = ec2.describe_key_pairs()['KeyPairs']
        assert len(currentkeypairs) == 1
        keypairs.append(currentkeypairs)

    # this must be the same keypair for every region
    # FIXME: sad that moto deals different fingerprints to the keys
    for keypair in keypairs[1:]:
        assert keypair[0]['KeyName'] == keypairs[0][0]['KeyName']


@pytest.mark.parametrize('regionscount', [2])
def test_chainmaker_calls_mints(monkeypatch, mockossystem, mocksubprocess, mockregions, ethermint_version,
                                mockamibuilder, tmp_files_dir, moto):
    # mock out all reading of *mint calls results
    monkeypatch.setattr('chainmaker.fill_validators', MagicMock)
    chainmaker = Chainmaker()
    chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    calls = mockossystem.call_args_list

    ethermint_calls = filter(lambda call: all(x in call[0][0] for x in ["ethermint -datadir", "init"]), calls)
    tendermint_calls = filter(lambda call: "tendermint gen_validator | tail -n +3 > " in call[0][0], calls)

    assert len(ethermint_calls) == 1
    assert len(tendermint_calls) == len(mockregions)


@pytest.mark.parametrize('regionscount', [1])
def test_checks_ethermint_version(chainmaker, mocksubprocess, mockregions, ethermint_version):
    # we're intercepting the call to get remote ethermint version to pretend its right or wrong

    # good version
    chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    # unexpectedly, bad version
    mocksubprocess.side_effect = lambda *args, **kwargs: "badbadbad" if "get_ethermint_version.sh" in args[0] else ''
    with pytest.raises(RuntimeError):
        chainmaker.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")


@pytest.mark.parametrize('regionscount', [1])
def test_local_ethermint_version(chainmaker, mocksubprocess, mockregions):
    def local_ethermint_version(*args, **kwargs):
        if "get_ethermint_version.sh" in args[0] or "rev-parse HEAD" in args[0]:
            return "01230123012301230123012301230123"
        else:
            return ''
    mocksubprocess.side_effect = local_ethermint_version

    # good version
    chainmaker.create_ethermint_network(mockregions, "local", "master_pub_key")