import logging
import os

import boto3

from chainmaker import Chainmaker
from settings import DEFAULT_DEVICE, DEFAULT_REGION
from utils import get_shh_key_file

logger = logging.getLogger(__name__)


class Chainshotter:
    def __init__(self):
        self.ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
        self.ec2_client = boto3.client('ec2')

    def chainshot(self, name, instances, clean_up=True):
        """
        Allows to snapshot a chain and save a json file with all chainshot info

        :param clean_up: indicates if instances should be terminated after snapshot is taken
        :param name: the name (ID) of the snapshot
        :param instances: the list of instance objects to be snapshotted
        :return: a dictionary containing the snapshot info
        """

        results = {
            "chainshot_name": name,
            "instances": []
        }

        for instance in instances:
            volumes_collection = instance.volumes.filter(Filters=
                                                  [
                                                      {'Name': 'tag-key', 'Values': ["Name"]},
                                                      {'Name': 'tag-value', 'Values': ['ethermint_volume']}
                                                  ]
            )
            volume = list(volumes_collection)[0]

            logger.info("Creating snapshot of volume {} of instance {}".format(volume.id, instance.id))

            snapshot = self.ec2.create_snapshot(VolumeId=volume.id, Description='ethermint-backup')
            logger.info("Created snapshot {}".format(snapshot.id))

            snapshot_info = {
                "instance": {
                    "id": instance.id,
                    "region": instance.placement["AvailabilityZone"],
                    "ami": instance.image_id,
                    "tags": instance.tags,
                    "vpc_id": instance.vpc_id,
                    "security_groups": [group["GroupName"] for group in instance.security_groups],
                    "key_name": instance.key_name,
                },
                "snapshot": {
                    # are those accurate?
                    # NOTE if we want to repeat chainshot() - thaw() multiple times,
                    # we need to save the launch time in S3, so that it is not reset each time an instance is run
                    "from": instance.launch_time.isoformat(),
                    "to": snapshot.start_time.isoformat(),

                    "id": snapshot.id
                }
            }
            results["instances"].append(snapshot_info)

            if clean_up:
                volume.delete()
                instance.terminate()

        logger.info("Finished chainshotting, the results:")
        logger.info(results)

        return results

    def thaw(self, chainshot):
        """
        Allows to unfreeze a chain using configuration file. For each snapshot/instance in the file,
        it restarts the instance (by creating a new instance with the same parameters) and attaches the snapshot
        as volume and mounts it

        :param chainshot: the config created by chainshot()
        :return: a list of AWS instances
        """
        instances = []

        for snapshot_info in chainshot["instances"]:
            new_instance = Chainmaker.create_ec2s_from_json(snapshot_info["instance"])[0]
            logger.info("Created new instance {} from AMI {}".format(new_instance.id, snapshot_info["instance"]["ami"]))

            volume = self.ec2.create_volume(SnapshotId=snapshot_info["snapshot"]["id"],
                                            AvailabilityZone=new_instance.placement["AvailabilityZone"])

            # time.sleep(10)  # let things settle

            new_instance.attach_volume(VolumeId=volume.id, Device=DEFAULT_DEVICE)
            logger.info("Attached volume {} containing snapshot {} to instance {}".format(volume.id,
                                                                                          snapshot_info["snapshot"][
                                                                                              "id"],
                                                                                          new_instance.id))

            instances.append(new_instance)

            logger.info("Running ./mount_snapshot.sh on instance {}".format(new_instance.id))
            mount_snapshot_command = lambda ssh_key, ip: \
                "ssh -o StrictHostKeyChecking=no -i {0} ubuntu@{1} 'bash -s' < mount_snapshot.sh".format(ssh_key, ip)
            os.system(mount_snapshot_command(get_shh_key_file(snapshot_info["instance"]["key_name"]),
                                             new_instance.public_ip_address))
            logger.info("Snapshot mounted successfully")

        return instances
