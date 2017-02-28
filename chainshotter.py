import json
import logging
import os
import time

import boto3

from chainmaker import Chainmaker
from settings import DEFAULT_DEVICE, DEFAULT_REGION, \
    DEFAULT_KEYS_LOCATION

logger = logging.getLogger(__name__)


class Chainshotter:
    def __init__(self):
        self.ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
        self.ec2_client = boto3.client('ec2')

    def chainshot(self, name, instances, filename="chainshot_info.json"):
        """
        Allows to snapshot a chain and save a json file with all chainshot info

        :param name: the name (ID) of the snapshot
        :param instances: the list of instances to be snapshotted
        :param filename: the file where the results are saved
        :return: a dictionary containing the snapshot info
        """

        results = {
            "chainshot_name": name,
            "instances": []
        }

        for instance in instances:
            # TODO choose the appropriate volume (by tags? device?)
            volume = instance.volumes.all()[0]

            snapshot = self.ec2.create_snapshot(VolumeId=volume.id, Description='ethermint-backup')

            snapshot_info = {
                "instance": {
                    "id": instance.id,
                    "region": instance.placement["AvailabilityZone"],
                    "ami": instance.image_id,
                    "tags": instance.tags,
                    "vpc_id": instance.vpc_id,
                    "security_groups": instance.security_groups,
                    "key_name": instance.key_name,
                },
                "snapshot": {
                    # are those accurate?
                    "snapshot_from": instance.created,
                    "snapshot_to": snapshot.start_time,

                    "snapshot_id": snapshot.id
                }
            }
            results[instances].append(snapshot_info)

        logger.info(results)

        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)

        return results

    def thaw(self, chainshot_file):
        """
        Allows to unfreeze a chain using configuration file. For each snapshot/instance in the file,
        it restarts the instance (by creating a new instance with the same parameters) and attaches the snapshot
        as volume and mounts it

        :param chainshot_file: the config file created by chainshot()
        :return: a list of AWS instances
        """
        chain_maker = Chainmaker()
        instances = []

        with open(chainshot_file) as json_data:
            chainshot = json.load(json_data)
            for snapshot_info in chainshot:
                new_instance = chain_maker.from_json(snapshot_info["instance"])
                volume = self.ec2.create_volume(SnapshotId=snapshot_info["snapshot"]["id"],
                                                AvailabilityZone=new_instance.placement["AvailabilityZone"])

                time.sleep(10)  # let things settle

                new_instance.attach_volume(VolumeId=volume.id, Device=DEFAULT_DEVICE)
                instances.append(new_instance)

                # run ./mount_snapshot.sh
                mount_snapshot_command = lambda ssh_key, ip: \
                    "ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} 'bash -s' < mount_snapshot.sh".format(ssh_key, ip)
                os.system(mount_snapshot_command(self._get_shh_key_file(snapshot_info["instance"]["key_name"]),
                                                 new_instance.public_ip_address))

        return instances

    def _get_shh_key_file(self, filename):
        """
        A helper funtion which allows to find an SSH key file using the filename
        :param filename:
        :return: a full path of the key
        """
        full_filepath = os.path.join(DEFAULT_KEYS_LOCATION, filename)
        if not os.path.exists(full_filepath):
            raise Exception("Key file {} missing".format(full_filepath))
        return full_filepath
