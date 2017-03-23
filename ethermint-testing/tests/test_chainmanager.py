import os
import re
import time

import boto3
import pytest
from mock.mock import MagicMock

from chainmanager import Chainmanager
from settings import DEFAULT_DEVICE, DEFAULT_PORTS, DEFAULT_LIVENESS_THRESHOLD
from tendermint_app_interface import Block
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


def test_creating_ethermint_network(chainmanager, mockami, mockregions, ethermint_version):
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    distinct_regions = set(mockregions)
    instances_in_regions = {}
    for r in mockregions:
        instances_in_regions[r] = instances_in_regions.get(r, 0) + 1

    for region in distinct_regions:
        ec2 = boto3.resource('ec2', region_name=region)
        assert len(list(ec2.instances.all())) == instances_in_regions[region]

    # check if nodes have the correct AMI
    for node in chain.instances:
        assert node.image_id == mockami
        # TODO check if image has correct tags?


def test_creating_ethermint_network_failures(chainmanager):
    pass


def test_ethermint_network_security_group(chainmanager, mockregions, ethermint_version):
    # test if nodes in the network can talk to each other (are in the same security group)
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    for node in chain.instances:
        ec2 = boto3.resource('ec2', region_name=node.region_name)
        node_sec_groups = [group["GroupId"] for group in node.security_groups]
        assert len(node_sec_groups) == 1

        security_group_ports = [range(ip_perm["FromPort"], ip_perm["ToPort"] + 1)
                                for ip_perm in ec2.SecurityGroup(node_sec_groups[0]).ip_permissions]
        security_group_ports = [item for sublist in security_group_ports for item in sublist]  # flatten list of lists
        assert sorted(security_group_ports) == sorted(DEFAULT_PORTS)


def test_ethermint_network_creates_AMIs(chainmanager, mockregions, mockamibuilder, ethermint_version):
    compare_ami_name = "test_ethermint{}_ami-ssh".format(ethermint_version[:8])
    chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    distinct_regions = set(mockregions)
    for region in distinct_regions:
        mockamibuilder.create_ami.assert_any_call(ethermint_version, compare_ami_name, regions=[region])


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_uses_existing_AMIs_when_exist(chainmanager, mockregions, mockamibuilder, create_mock_amis,
                                                         ethermint_version):
    chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    mockamibuilder.create_ami.reset_mock()

    chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    mockamibuilder.create_ami.assert_not_called()

    chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key", no_ami_cache=True)
    mockamibuilder.create_ami.assert_called()


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_new_AMIs_for_ethermint_versions(chainmanager, mockregions, mockamibuilder, create_mock_amis,
                                                   ethermint_version, mocksubprocess):
    chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    mockamibuilder.create_ami.reset_mock()

    other_version = "otherohterotherohterotherohter"
    mocksubprocess.side_effect = lambda *args, **kwargs: other_version if "get_ethermint_version.sh" in args[0] else ''
    chainmanager.create_ethermint_network(mockregions, other_version, "master_pub_key")
    mockamibuilder.create_ami.assert_called()


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_find_AMI(chainmanager, mockregions, mockamibuilder, create_mock_amis, ethermint_version):
    chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    mockamibuilder.create_ami.reset_mock()

    new_region = "us-gov-west-1"
    mockregions += [new_region]

    chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    calls = mockamibuilder.create_ami.call_args_list
    assert len(calls) == 1
    assert calls[0][1]['regions'] == [new_region]


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_attaches_volumes(chainmanager, mockregions, ethermint_version):
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    for node in chain.instances:
        assert len(node.block_device_mappings) == 2  # the default drive and our additional drive
        found_our_volume = False
        for bdm in node.block_device_mappings:
            if bdm["DeviceName"] == DEFAULT_DEVICE:
                found_our_volume = True
                break
        assert found_our_volume


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_mounts_volumes(chainmanager, mockregions, mocksubprocess, ethermint_version):
    # mount has to be done manually since the boto3 interface does not allow to do this
    # for now, testing if ssh command is correct
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    for node in chain.instances:
        mocksubprocess.assert_any_call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                       "'bash -s' < shell_scripts/mount_new_volume.sh".format(
            get_shh_key_file(node.key_name), node.public_ip_address),
            shell=True)


@pytest.mark.parametrize('regionscount', [2])
def test_get_roster_all_nodes(chainmanager, mockregions, ethermint_version):
    chain1 = chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    chain2 = chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    roster = chainmanager.get_roster([chain1, chain2])

    assert len(roster) == 2 * len(mockregions)


@pytest.mark.parametrize('regionscount', [1])
def test_get_roster_good_node(chainmanager, mockregions, ethermint_version):
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    roster = chainmanager.get_roster([chain])

    node_name = roster.keys()[0]

    # sensible node name
    assert mockregions[0] in node_name
    assert chain.instances[0].id in node_name

    node = roster[node_name]

    assert node['host'] == chain.instances[0].public_ip_address


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_prepares_for_ethermint(chainmanager, mockregions, mocksubprocess, mockossystem,
                                                  tmp_files_dir, ethermint_version):
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")
    ethermint_files_location = os.path.join(tmp_files_dir, "ethermint")

    for i, node in enumerate(chain.instances):
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
def test_ethermint_network_runs_ethermint(chainmanager, mockregions, mocksubprocess,
                                          ethermint_version):
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    first = None
    for node in chain.instances:
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


@pytest.fixture()
def chain(chainmanager, mockregions, ethermint_version):
    return chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")


@pytest.fixture()
def mock_ethermint_requests(requests_mock):
    def _mock(height, time, apphash, ip_list):
        for ip in ip_list:
            requests_mock.add(requests_mock.GET, re.compile(r'http://' + ip + r':46657/status'),
                              json={"result": [0, {"latest_block_height": height, "latest_block_time": time,
                                                   "latest_app_hash": apphash}]},
                              status=200)

            requests_mock.add(requests_mock.POST, re.compile(r'http://' + ip + r':8545'),
                              json={"result": {"number": hex(height - 1), "hash": "0x" + apphash,
                                               "timestamp": hex(int(time))}},
                              status=200)
    return _mock


@pytest.mark.parametrize('regionscount', [2])
def test_get_status(chainmanager, chain, mock_ethermint_requests):
    height = 123
    t = time.time() * 1e9  # create blocks that are alive
    mock_ethermint_requests(height, t, "hash", [inst.public_ip_address for inst in chain.instances])

    result = chainmanager.get_status(chain)
    assert result["is_alive"]
    assert result["height"] == height

    instance = chain.instances[0]
    result_instance = result['nodes'][0]
    assert result_instance['instance_id'] == instance.id
    assert result_instance['instance_region'] == instance.region_name
    assert result_instance['name'] == instance.instance_name
    assert result_instance['height'] == height
    assert result_instance['last_block_time'] == t
    assert result_instance['last_block_height'] == height
    assert result_instance['is_alive']


@pytest.mark.parametrize('regionscount', [2])
def test_get_status_all_dead(chainmanager, chain, mock_ethermint_requests):
    t = time.time() * 1e9 - DEFAULT_LIVENESS_THRESHOLD  # create too old blocks
    mock_ethermint_requests(123, t, "hash", [inst.public_ip_address for inst in chain.instances])

    result = chainmanager.get_status(chain)
    assert not result["is_alive"]
    assert len(result["nodes"]) == len(chain.instances)
    for instance in result['nodes']:
        assert not instance['is_alive']
        assert instance['last_block_time'] == t


@pytest.mark.parametrize('regionscount', [2])
def test_get_status_one_dead(chainmanager, chain, mock_ethermint_requests):
    mock_ethermint_requests(123, time.time() * 1e9, "hash", [inst.public_ip_address for inst in chain.instances[1:]])
    mock_ethermint_requests(123, time.time() * 1e9 - 2 * DEFAULT_LIVENESS_THRESHOLD, "hash",
                            [chain.instances[0].public_ip_address])

    result = chainmanager.get_status(chain)
    assert not result["is_alive"]
    assert len(filter(lambda instance: not instance['is_alive'], result['nodes'])) == 1


@pytest.mark.parametrize('regionscount', [1])
def test_get_status_ethermint_out_of_sync(chainmanager, chain):
    pass


@pytest.mark.parametrize('regionscount', [5, 6])
def test_get_status_average_height(chainmanager, chain, regionscount):
    current = {"value": 1}

    def get_latest_block(*args):
        block = Block("hash", time=time.time() * 1e9, height=current["value"])
        current["value"] += 1
        return block

    chain.chain_interface.get_latest_block = MagicMock(side_effect=get_latest_block)

    result = chainmanager.get_status(chain)
    assert result["is_alive"]
    assert result["height"] == (regionscount + 1) / 2


@pytest.mark.parametrize('regionscount', [2])
@pytest.mark.parametrize("pathcheck", ["tendermint version", "ethermint -h", "packer version"])
def test_check_path(chainmanager, mockregions, mockossystem, pathcheck, ethermint_version):
    chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    mockossystem.assert_any_call(pathcheck)


def test_chainmanager_imports_keypairs(chainmanager, mockregions, ethermint_version):
    chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

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
def test_chainmanager_calls_mints(monkeypatch, mockossystem, mocksubprocess, mockregions, ethermint_version,
                                  mockamibuilder, tmp_files_dir, moto):
    # mock out all reading of *mint calls results
    monkeypatch.setattr('chainmanager.fill_validators', MagicMock)
    chainmanager = Chainmanager()
    chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    calls = mockossystem.call_args_list

    ethermint_calls = filter(lambda call: all(x in call[0][0] for x in ["ethermint -datadir", "init"]), calls)
    tendermint_calls = filter(lambda call: "tendermint gen_validator | tail -n +3 > " in call[0][0], calls)

    assert len(ethermint_calls) == 1
    assert len(tendermint_calls) == len(mockregions)


@pytest.mark.parametrize('regionscount', [1])
def test_checks_ethermint_version(chainmanager, mocksubprocess, mockregions, ethermint_version):
    # we're intercepting the call to get remote ethermint version to pretend its right or wrong

    # good version
    chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")

    # unexpectedly, bad version
    mocksubprocess.side_effect = lambda *args, **kwargs: "badbadbad" if "get_ethermint_version.sh" in args[0] else ''
    with pytest.raises(RuntimeError):
        chainmanager.create_ethermint_network(mockregions, ethermint_version, "master_pub_key")


@pytest.mark.parametrize('regionscount', [1])
def test_local_ethermint_version(chainmanager, mocksubprocess, mockregions):
    def local_ethermint_version(*args, **kwargs):
        if "get_ethermint_version.sh" in args[0] or "rev-parse HEAD" in args[0]:
            return "01230123012301230123012301230123"
        else:
            return ''

    mocksubprocess.side_effect = local_ethermint_version

    # good version
    chainmanager.create_ethermint_network(mockregions, "local", "master_pub_key")
