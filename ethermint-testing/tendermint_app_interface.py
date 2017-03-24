import json
from datetime import datetime

import requests


class EthermintException(Exception):
    def __init__(self, message):
        super(EthermintException, self).__init__(message)


class TendermintBlock:
    def __init__(self, data):
        if "block" in data:
            header = data["block"]["header"]
            self.hash = header["app_hash"]
            self.height = header["height"]
            self.time = header["time"]
        elif "latest_app_hash" in data:
            self.hash = data["latest_app_hash"]
            self.height = data["latest_block_height"]
            self.time = data["latest_block_time"]
        else:
            raise ValueError("Unable to create TendermintBlock from {}".format(data))

		# post-process
		self.hash = self.hash.upper()
		self.time = datetime.fromtimestamp(self.time / 1e9)


class GethBlock:
    def __init__(self, data):
        self.hash = data["hash"][2:].upper()
        self.height = int(data["number"], 16)
        self.time = datetime.fromtimestamp(int(data["timestamp"], 16))


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
            r = TendermintAppInterface.prepare_rpc_result(raw)

            return TendermintBlock(r)

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
