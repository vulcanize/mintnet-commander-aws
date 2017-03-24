import json
from datetime import datetime

import requests


class EthermintException(Exception):
    def __init__(self, message):
        super(EthermintException, self).__init__(message)


class Block:
    def __init__(self, hash, height=None, time=None):
        self.hash = hash.upper()
        self.height = height
        self.time = time  # datetime object


class TendermintAppInterface:
    @staticmethod
    def rpc(ip):
        return "http://{}:46657".format(ip)

    @staticmethod
    def get_latest_block(ec2_instance):
        r = requests.get(TendermintAppInterface.rpc(ec2_instance.public_ip_address) + "/status").json()['result'][1]
        t = datetime.fromtimestamp(r["latest_block_time"] / 1e9)
        block = Block(r["latest_app_hash"], height=r["latest_block_height"], time=t)
        return block


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
    def get_latest_block(ec2_instance):
        tendermint_latest_block = super(EthermintInterface, EthermintInterface).get_latest_block(ec2_instance)
        ethermint_height = tendermint_latest_block.height - 1

        r = EthermintInterface._request(ec2_instance, "eth_getBlockByNumber", [str(ethermint_height), False])['result']
        height = int(r["number"], 16)
        last_ethereum_block = Block(r["hash"][2:], height=height, time=datetime.fromtimestamp(int(r["timestamp"], 16)))

        if last_ethereum_block.height + 1 != tendermint_latest_block.height \
                or last_ethereum_block.hash != tendermint_latest_block.hash:
            raise EthermintException("Geth/tendermint not in sync in instance {}".format(ec2_instance.id))
        return tendermint_latest_block