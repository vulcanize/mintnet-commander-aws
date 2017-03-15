import logging

import boto3

from chainmaker import Chainmaker
from instance_creator import InstanceCreator
from settings import DEFAULT_DEVICE
from utils import run_sh_script, get_region_name
from waiting_for_ec2 import wait_for_detached, wait_for_available_volume

logger = logging.getLogger(__name__)


class Chainshotter:
    def __init__(self, num_processes=None):
        self.instance_creator = InstanceCreator(num_processes)

    def chainshot(self, name, region_instances, clean_up=False):
        """
        Allows to snapshot a chain and save a json file with all chainshot info

        :param clean_up: indicates if instances should be terminated after snapshot is taken
        :param name: the name (ID) of the snapshot
        :param instances_ids_map: the map of instance IDs pointing to regions where they're located
        :return: a dictionary containing the snapshot info
        """
        results = {
            "chainshot_name": name,
            "instances": []
        }
        for pair in region_instances:
            all_ids = [instance.id for instance in list(pair.ec2.instances.all())]
            if pair.id not in all_ids:
                raise IndexError("Instance {} not found in region {}".format(pair.id, pair.region_name))

        instances = [pair.instance for pair in region_instances]

        Chainmaker._halt_ethermint(instances)

        for pair in region_instances:
            instance = pair.instance
            volumes_collection = instance.volumes.filter(Filters=
            [
                {'Name': 'tag-key', 'Values': ["Name"]},
                {'Name': 'tag-value', 'Values': ['ethermint_volume']}
            ]
            )
            volume = list(volumes_collection)[0]

            snapshot_info = self._snapshot(instance, volume, pair.ec2)

            results["instances"].append(snapshot_info)

            if clean_up:
                run_sh_script("shell_scripts/unmount_new_volume.sh", instance.key_name, instance.public_ip_address)
                instance.detach_volume(VolumeId=volume.id, Force=True)  # FIXME the device is stuck in detaching state
                wait_for_detached(volume, instance)
                volume.delete()
                instance.terminate()

        Chainmaker._run_ethermint(instances)

        logger.info("Finished chainshotting, the results:")
        logger.info(results)

        return results

    def _snapshot(self, instance, volume, ec2):
        logger.info("Creating snapshot of volume {} of instance {}".format(volume.id, instance.id))

        snapshot = ec2.create_snapshot(VolumeId=volume.id, Description='ethermint-backup')
        snapshot.wait_until_completed()
        logger.info("Created snapshot {}".format(snapshot.id))

        snapshot_info = {
            "instance": {
                "id": instance.id,
                "region": get_region_name(instance.placement["AvailabilityZone"]),
                "availablility_zone": instance.placement["AvailabilityZone"],
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
        return snapshot_info

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
            ec2 = boto3.resource('ec2', region_name=snapshot_info["instance"]["region"])
            new_instance = self.instance_creator.create_ec2s_from_json([snapshot_info["instance"]])[0]
            logger.info("Created new instance {} from AMI {}".format(new_instance.id, snapshot_info["instance"]["ami"]))

            snapshot = ec2.Snapshot(snapshot_info["snapshot"]["id"])

            volume = ec2.create_volume(SnapshotId=snapshot.id,
                                       AvailabilityZone=new_instance.placement["AvailabilityZone"])

            wait_for_available_volume(volume, get_region_name(new_instance.placement["AvailabilityZone"]))

            new_instance.attach_volume(VolumeId=volume.id, Device=DEFAULT_DEVICE)
            logger.info("Attached volume {} containing snapshot {} to instance {}".format(volume.id,
                                                                                          snapshot.id,
                                                                                          new_instance.id))

            instances.append(new_instance)

            run_sh_script("shell_scripts/mount_snapshot.sh", snapshot_info["instance"]["key_name"],
                          new_instance.public_ip_address)

        for instance in instances:
            logger.info("Instance ID: {} unfreezed from chainshot".format(instance.id))

        Chainmaker._run_ethermint(instances)
        logger.info("Done starting ethermint on instances")

        return instances
