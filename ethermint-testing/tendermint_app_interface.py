import json
from datetime import datetime

import dateutil
import pytz
import requests


class EthermintException(Exception):
    def __init__(self, message):
        super(EthermintException, self).__init__(message)


class TendermintBlock:
    def __init__(self, data):
        if "header" in data:
            header = data["header"]
            self.hash = header["app_hash"]
            self.height = header["height"]
            self.time = header["time"]
        elif "latest_app_hash" in data:
            self.hash = data["latest_app_hash"]
            self.height = data["latest_block_height"]
            self.time = datetime.fromtimestamp(data["latest_block_time"] / 1e9, tz=pytz.UTC)
        else:
            raise ValueError("Unable to create TendermintBlock from {}".format(data))

        # post-process
        self.hash = self.hash.upper()


class GethBlock:
    def __init__(self, data):
        self.hash = data["hash"][2:].upper()
        self.height = int(data["number"], 16)
        self.time = datetime.fromtimestamp(int(data["timestamp"], 16), tz=pytz.UTC)


class TendermintAppInterface:
    @staticmethod
    def prepare_rpc_result(raw):
        return raw.json()['result'][1]

    @staticmethod
    def get_block(ec2_instance, block=None):
        """
        :param block: None for latest
        """
        if block is None:
            raw = requests.get(TendermintAppInterface.rpc(ec2_instance.public_ip_address) + "/status")
            r = TendermintAppInterface.prepare_rpc_result(raw)
            return TendermintBlock(r)
        else:
            raw = requests.get("{}/block?height={}".format(TendermintAppInterface.rpc(ec2_instance.public_ip_address),
                                                           block))
            r = TendermintAppInterface.prepare_rpc_result(raw)["block"]

            return TendermintBlock(r)

    @staticmethod
    def get_blocks(ec2_instance, fromm, to):
        request_template = "{}/blockchain?minHeight={}&maxHeight={}"
        raw = requests.get(request_template.format(TendermintAppInterface.rpc(ec2_instance.public_ip_address),
                                                   fromm,
                                                   to))
        r = TendermintAppInterface.prepare_rpc_result(raw)['block_metas']

        return [TendermintBlock(block_meta) for block_meta in r]


    @staticmethod
    def rpc(ip):
        return "http://{}:46657".format(ip)


class EthermintInterface(object, TendermintAppInterface):
    request_id = 0

    @staticmethod
    def _get_request_id():
        current_id = EthermintInterface.request_id
        EthermintInterface.request_id += 1
        return current_id

    @staticmethod
    def _request(ec2_instance, method, params=None):
        data = json.dumps({"jsonrpc": "2.0", "method": method, "params": params or [],
                           "id": EthermintInterface._get_request_id()})
        response = requests.post(EthermintInterface.rpc(ec2_instance.public_ip_address), data=data)
        return response.json()

    @staticmethod
    def rpc(ip):
        return "http://{}:8545".format(ip)

    @staticmethod
    def get_block(ec2_instance, block=None):
        """
        Note that this checks block integrity between TM and ETH, while get_blocks doesn't
        :param block: None for latest
        """
        tendermint_latest_block = super(EthermintInterface, EthermintInterface).get_block(ec2_instance, block)
        ethermint_height = tendermint_latest_block.height - 1

        r = EthermintInterface._request(ec2_instance, "eth_getBlockByNumber", [str(ethermint_height), False])['result']
        last_ethereum_block = GethBlock(r)

        if last_ethereum_block.height + 1 != tendermint_latest_block.height:
            raise EthermintException("Geth/tendermint not in sync in instance {} (height)".format(ec2_instance.id))
        if last_ethereum_block.hash != tendermint_latest_block.hash:
            raise EthermintException("Geth/tendermint not in sync in instance {} (hash)".format(ec2_instance.id))
        return tendermint_latest_block

    @staticmethod
    def get_blocks(ec2_instance, fromm, to):
        """
        Doesn't check TM-ETH integrity of blocks
        :return: list
        """
        return super(EthermintInterface, EthermintInterface).get_blocks(ec2_instance, fromm, to)
