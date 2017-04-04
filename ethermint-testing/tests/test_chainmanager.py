import os
import re
from datetime import datetime, timedelta

import boto3
import pytest
import pytz
from mock.mock import MagicMock

from chainmanager import Chainmanager, NETWORK_FAULT_PREPARATION_TIME_PER_INSTANCE
from settings import DEFAULT_DEVICE, DEFAULT_PORTS, DEFAULT_LIVENESS_THRESHOLD
from tendermint_app_interface import EthermintException
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
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version)

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
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version)

    for node in chain.instances:
        ec2 = boto3.resource('ec2', region_name=node.region_name)
        node_sec_groups = [group["GroupId"] for group in node.security_groups]
        assert len(node_sec_groups) == 1

        security_group_ports = [(range(ip_perm["FromPort"], ip_perm["ToPort"] + 1), ip_perm["IpProtocol"])
                                for ip_perm in ec2.SecurityGroup(node_sec_groups[0]).ip_permissions]
        security_group_ports = [(port, protocol) for (sublist, protocol) in security_group_ports for port in sublist]
        assert sorted(security_group_ports) == sorted(DEFAULT_PORTS)


def test_ethermint_network_creates_AMIs(chainmanager, mockregions, mockamibuilder, ethermint_version):
    compare_ami_name = "test_ethermint{}_ami-ssh".format(ethermint_version[:8])
    chainmanager.create_ethermint_network(mockregions, ethermint_version)

    distinct_regions = set(mockregions)
    for region in distinct_regions:
        mockamibuilder.create_ami.assert_any_call(ethermint_version, compare_ami_name, regions=[region])


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_uses_existing_AMIs_when_exist(chainmanager, mockregions, mockamibuilder, create_mock_amis,
                                                         ethermint_version):
    chainmanager.create_ethermint_network(mockregions, ethermint_version)
    mockamibuilder.create_ami.reset_mock()

    chainmanager.create_ethermint_network(mockregions, ethermint_version)
    mockamibuilder.create_ami.assert_not_called()

    chainmanager.create_ethermint_network(mockregions, ethermint_version, no_ami_cache=True)
    mockamibuilder.create_ami.assert_called()


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_new_AMIs_for_ethermint_versions(chainmanager, mockregions, mockamibuilder, create_mock_amis,
                                                   ethermint_version, mocksubprocess):
    chainmanager.create_ethermint_network(mockregions, ethermint_version)
    mockamibuilder.create_ami.reset_mock()

    other_version = "otherohterotherohterotherohter"
    mocksubprocess.side_effect = lambda *args, **kwargs: other_version if "get_ethermint_version.sh" in args[0] else ''
    chainmanager.create_ethermint_network(mockregions, other_version)
    mockamibuilder.create_ami.assert_called()


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_find_AMI(chainmanager, mockregions, mockamibuilder, create_mock_amis, ethermint_version):
    chainmanager.create_ethermint_network(mockregions, ethermint_version)
    mockamibuilder.create_ami.reset_mock()

    new_region = "us-gov-west-1"
    mockregions += [new_region]

    chainmanager.create_ethermint_network(mockregions, ethermint_version)
    calls = mockamibuilder.create_ami.call_args_list
    assert len(calls) == 1
    assert calls[0][1]['regions'] == [new_region]


@pytest.mark.parametrize('regionscount', [2])
def test_ethermint_network_attaches_volumes(chainmanager, mockregions, ethermint_version):
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version)

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
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version)

    for node in chain.instances:
        mocksubprocess.assert_any_call("ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} "
                                       "'bash -s' < shell_scripts/mount_new_volume.sh".format(
            get_shh_key_file(node.key_name), node.public_ip_address),
            shell=True)


@pytest.mark.parametrize('regionscount', [2])
def test_get_roster_all_nodes(chainmanager, mockregions, ethermint_version):
    chain1 = chainmanager.create_ethermint_network(mockregions, ethermint_version)
    chain2 = chainmanager.create_ethermint_network(mockregions, ethermint_version)

    roster = chainmanager.get_roster([chain1, chain2])

    assert len(roster) == 2 * len(mockregions)


@pytest.mark.parametrize('regionscount', [1])
def test_get_roster_good_node(chainmanager, mockregions, ethermint_version):
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version)

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
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version)
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
    chain = chainmanager.create_ethermint_network(mockregions, ethermint_version)

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
    return chainmanager.create_ethermint_network(mockregions, ethermint_version)


@pytest.fixture()
def mock_ethermint_requests(requests_mock):
    """
    A decorated fixture which allows to mock HTTP requests made by tendermintApp interface and ethermint interface;
    the resulting responses will never create out-of-sync status of geth and tendermint
    """
    def _mock(height, time, apphash, ip_list):
        """
        Mocks requests to certain entrypoints;
        :param height: the last block height
        :param time: the last block time
        :param apphash: the hash of the last geth block
        :param ip_list: the list of the IPs which will be queried
        :return:
        """
        for ip in ip_list:
            requests_mock.add(requests_mock.GET, re.compile(r'http://' + ip + r':46657/status'),
                              json={"result": [0, {"latest_block_height": height,
                                                   "latest_block_time": to_timestamp(time) * 1e9,
                                                   "latest_app_hash": apphash}]},
                              status=200)

            requests_mock.add(requests_mock.POST, re.compile(r'http://' + ip + r':8545'),
                              json={"result": {"number": hex(height - 1), "hash": "0x" + apphash,
                                               "timestamp": hex(int(to_timestamp(time)))}},
                              status=200)
    return _mock


@pytest.mark.parametrize('regionscount', [2])
def test_get_status(chainmanager, chain, mock_ethermint_requests):
    height = 123
    t = datetime.now(tz=pytz.UTC)  # create blocks that are alive
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
    assert result_instance['last_block_time'] == t.isoformat()
    assert result_instance['last_block_height'] == height
    assert result_instance['is_alive']


def to_timestamp(dt):
    return (dt - datetime(1970, 1, 1, tzinfo=pytz.UTC)).total_seconds()


@pytest.mark.parametrize('regionscount', [2])
def test_get_status_one_dead(chainmanager, chain, mock_ethermint_requests):
    mock_ethermint_requests(123, datetime.now(tz=pytz.UTC), "hash", [inst.public_ip_address for inst in chain.instances[1:]])
    mock_ethermint_requests(123, datetime.now(tz=pytz.UTC) - DEFAULT_LIVENESS_THRESHOLD, "hash",
                            [chain.instances[0].public_ip_address])

    result = chainmanager.get_status(chain)
    assert not result["is_alive"]
    assert len(filter(lambda instance: not instance['is_alive'], result['nodes'])) == 1


@pytest.mark.parametrize('regionscount', [1])
def test_get_status_ethermint_out_of_sync(chainmanager, chain, requests_mock):
    ip = chain.instances[0].public_ip_address
    height = 123
    apphash = "hash"
    t = datetime.now(tz=pytz.UTC)

    # different hashes
    requests_mock.add(requests_mock.GET, re.compile(r'http://' + ip + r':46657/status'),
                      json={"result": [0, {"latest_block_height": height, "latest_block_time": to_timestamp(t) * 1e9,
                                           "latest_app_hash": apphash + "0"}]},
                      status=200)

    requests_mock.add(requests_mock.POST, re.compile(r'http://' + ip + r':8545'),
                      json={"result": {"number": hex(height - 1), "hash": "0x" + apphash,
                                       "timestamp": hex(int(to_timestamp(t)))}},
                      status=200)

    with pytest.raises(EthermintException):
        chainmanager.get_status(chain)

    # no heights difference (geth H app hash should be in tendermint H+1 block)
    requests_mock.add(requests_mock.GET, re.compile(r'http://' + ip + r':46657/status'),
                      json={"result": [0, {"latest_block_height": height, "latest_block_time": to_timestamp(t) * 1e9,
                                           "latest_app_hash": apphash}]},
                      status=200)

    requests_mock.add(requests_mock.POST, re.compile(r'http://' + ip + r':8545'),
                      json={"result": {"number": hex(height), "hash": "0x" + apphash,
                                       "timestamp": hex(int(to_timestamp(t)))}},
                      status=200)

    with pytest.raises(EthermintException):
        chainmanager.get_status(chain)


@pytest.mark.parametrize('regionscount', [5, 6])
def test_get_status_average_height(chainmanager, chain, mock_ethermint_requests, regionscount):
    for i, instance in enumerate(chain.instances):
        mock_ethermint_requests(i + 1, datetime.now(tz=pytz.UTC), "hash", [instance.public_ip_address])

    result = chainmanager.get_status(chain)
    assert result["is_alive"]
    assert result["height"] == (regionscount + 1) / 2


@pytest.mark.parametrize('regionscount', [2])
@pytest.mark.parametrize("pathcheck", ["tendermint version", "ethermint -h", "packer version"])
def test_check_path(chainmanager, mockregions, mockossystem, pathcheck, ethermint_version):
    chainmanager.create_ethermint_network(mockregions, ethermint_version)

    mockossystem.assert_any_call(pathcheck)


def test_chainmanager_imports_keypairs(chainmanager, mockregions, ethermint_version):
    chainmanager.create_ethermint_network(mockregions, ethermint_version)

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
    chainmanager.create_ethermint_network(mockregions, ethermint_version)

    calls = mockossystem.call_args_list

    ethermint_calls = filter(lambda call: all(x in call[0][0] for x in ["ethermint -datadir", "init"]), calls)
    tendermint_calls = filter(lambda call: "tendermint gen_validator | tail -n +3 > " in call[0][0], calls)

    assert len(ethermint_calls) == 1
    assert len(tendermint_calls) == len(mockregions)


@pytest.mark.parametrize('regionscount', [1])
def test_checks_ethermint_version(chainmanager, mocksubprocess, mockregions, ethermint_version):
    # we're intercepting the call to get remote ethermint version to pretend its right or wrong

    # good version
    chainmanager.create_ethermint_network(mockregions, ethermint_version)

    # unexpectedly, bad version
    mocksubprocess.side_effect = lambda *args, **kwargs: "badbadbad" if "get_ethermint_version.sh" in args[0] else ''
    with pytest.raises(RuntimeError):
        chainmanager.create_ethermint_network(mockregions, ethermint_version)


@pytest.mark.parametrize('regionscount', [1])
def test_local_ethermint_version(chainmanager, mocksubprocess, mockregions):
    def local_ethermint_version(*args, **kwargs):
        if "get_ethermint_version.sh" in args[0] or "rev-parse HEAD" in args[0]:
            return "01230123012301230123012301230123"
        else:
            return ''

    mocksubprocess.side_effect = local_ethermint_version

    # good version
    chainmanager.create_ethermint_network(mockregions, "local")


@pytest.mark.parametrize('regionscount', [1])
def test_history_default_to_fromm(requests_mock, chain, mock_ethermint_requests):
    ip = chain.instances[0].public_ip_address
    t = datetime.now(tz=pytz.UTC)

    def reset_mocks():
        mock_ethermint_requests(10, t, "hash", [inst.public_ip_address for inst in chain.instances])
        requests_mock.add(requests_mock.GET,
                          re.compile(r'http://' + ip + r':46657/blockchain\?minHeight=9\&maxHeight=10'),
                          json={"result": [0, {'block_metas': [{'header': {'app_hash': "",
                                                                           'height': "",
                                                                           'time': t.isoformat()}}]}]},
                          status=200)

    reset_mocks()
    history1 = Chainmanager.get_history(chain, 9)

    reset_mocks()
    history2 = Chainmanager.get_history(chain)

    assert history1 == history2


@pytest.mark.parametrize('regionscount', [1])
def test_history_gets_blocks(requests_mock, chain):
    ip = chain.instances[0].public_ip_address
    t = datetime.now(tz=pytz.UTC)
    height = 18

    requests_mock.add(requests_mock.GET, re.compile(r'http://' + ip + r':46657/blockchain\?minHeight=1\&maxHeight=10'),
                      json={"result": [0, {'block_metas': 10 * [{'header': {'app_hash': "",
                                                                            'height': height,
                                                                            'time': t.isoformat()}}]}]},
                      status=200)

    history = Chainmanager.get_history(chain, 1, 10)

    check_history(history, 9, 0, height, t)


def check_history(history, expected_length, first_difference, first_height, first_time):
    """
    Does a quick check of history correctness, as returned by get_history
    :param history:
    :param expected_length: how many entries should it have
    :param first_difference: what should be the first block duration be, ie block time difference
    :param first_height: ...
    :param first_time: ... (datetime)
    :return:
    """
    assert len(history) == expected_length  # history is block intervals so 10 - 1
    assert history[0][0] == first_difference  # difference between t and t as all block are from time t
    assert history[0][1] == first_time.isoformat()
    assert history[0][2] == first_height  # fake height!


@pytest.mark.parametrize('regionscount', [1])
def test_history_invalid_from_to(chain):
    with pytest.raises(ValueError):
        Chainmanager.get_history(chain, 123, 1)


@pytest.mark.parametrize('regionscount', [2])
def test_history_loooks_at_first_node_only(chain, requests_mock):
    chain.instances[1] = None  # shouldn't interfere
    ip = chain.instances[0].public_ip_address
    t = datetime.now(tz=pytz.UTC)

    requests_mock.add(requests_mock.GET, re.compile(r'http://' + ip + r':46657/blockchain\?minHeight=1\&maxHeight=10'),
                      json={"result": [0, {'block_metas': 10 * [{'header': {'app_hash': "",
                                                                            'height': "",
                                                                            'time': t.isoformat()}}]}]},
                      status=200)

    Chainmanager.get_history(chain, 1, 10)


@pytest.mark.parametrize('regionscount', [2])
def test_network_fault(requests_mock, chain, mock_ethermint_requests, mocksubprocess):
    # FIXME: test-all smoke test for now, consider splitting into separate logical assertions
    ip = chain.instances[0].public_ip_address
    t = datetime.now(tz=pytz.UTC)

    mock_ethermint_requests(1, t, "hash", [ip])
    mock_ethermint_requests(10, t + timedelta(seconds=10), "hash2",
                            [inst.public_ip_address for inst in chain.instances])
    requests_mock.add(requests_mock.GET, re.compile(r'http://' + ip + r':46657/blockchain\?minHeight=1\&maxHeight=10'),
                      json={"result": [0, {'block_metas': 10 * [{'header': {'app_hash': "",
                                                                            'height': "",
                                                                            'time': t.isoformat()}}]}]},
                      status=200)

    # fake time when a remote machine should report having run it's tc command
    delay_step_time1 = (t+timedelta(seconds=5)).isoformat()
    delay_step_time2 = (t+timedelta(seconds=7)).isoformat()
    delay_step_time3 = (t+timedelta(seconds=7)).isoformat()

    def _side_effect(*args, **kwargs):
        if "get_datetime.sh" in args[0]:
            assert ip in args[0]  # only instance 0 is queried for date
            return t.isoformat()
        elif "run_tcs.sh" in args[0]:
            assert "run_tcs.sh 2 123 1 eth0 {}".format(
                (t+timedelta(seconds=(NETWORK_FAULT_PREPARATION_TIME_PER_INSTANCE * len(chain.instances)))).isoformat()
            ) in args[0]
            assert any([inst.public_ip_address in args[0] for inst in chain.instances])
            return "{}\n{}\n{}".format(delay_step_time1, delay_step_time2, delay_step_time3)

        assert False

    mocksubprocess.side_effect = _side_effect

    result = Chainmanager.get_network_fault(chain, 2, 123, 1)

    check_history(result["blocktimes"], 9, 0, "", t)
    assert len(result["delay_steps"]) == 3
    assert result["delay_steps"] == [
        (123, delay_step_time1),
        (246, delay_step_time2),
        (0, delay_step_time3)
    ]
