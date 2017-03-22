import json

import requests

from settings import TENDERMINT_RPC_ENDPOINT, GETH_RPC_ENDPOINT


class EthermintException(Exception):
    def __init__(self, message):
        super(EthermintException, self).__init__(message)


class Block:
    def __init__(self, hash, height=None, time=None):
        self.hash = hash.upper()
        self.height = height
        self.time = time


class TendermintAppInterface:
    @staticmethod
    def get_latest_block(ec2_instance):
        r = requests.get(TENDERMINT_RPC_ENDPOINT(ec2_instance.public_ip_address) + "/status").json()['result'][1]
        block = Block(r["latest_app_hash"], height=r["latest_block_height"] - 1, time=r["latest_block_time"])
        return block

    @staticmethod
    def get_block(ec2_instance, height):
        r = requests.get(TENDERMINT_RPC_ENDPOINT(ec2_instance.public_ip_address) + "/block?height=" + str(height)).json()['result'][1]
        block = Block(r["block"]["header"]["app_hash"], height=r["block"]["header"]["height"] - 1)  # TODO time
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
        response = requests.post(GETH_RPC_ENDPOINT(ec2_instance.public_ip_address), data=data)
        return response.json()

    @staticmethod
    def get_latest_block(ec2_instance):
        r = EthermintInterface._request(ec2_instance, "eth_getBlockByNumber", ["latest", False])['result']
        height = int(r["number"], 16)
        last_ethereum_block = Block(r["hash"][2:], height=height, time=int(r["timestamp"], 16))
        tendermint_block = super(EthermintInterface, EthermintInterface).get_block(ec2_instance, height)

        if last_ethereum_block.height != tendermint_block.height or last_ethereum_block.hash != tendermint_block.hash:
            raise EthermintException("Geth/tendermint not in sync in instance {}".format(ec2_instance.id))
        return last_ethereum_block

    @staticmethod
    def get_block(ec2_instance, height):
        raise NotImplementedError()
