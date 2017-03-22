import logging

import boto3

from chain import Chain
from chainmanager import RegionInstancePair
from instance_creator import InstanceCreator
from settings import DEFAULT_DEVICE
from utils import run_sh_script, get_region_name, run_ethermint, halt_ethermint
from waiting_for_ec2 import wait_for_detached, wait_for_available_volume

logger = logging.getLogger(__name__)


class Chainshotter:
    def __init__(self, num_processes=None):
        self.instance_creator = InstanceCreator(num_processes)

    def chainshot(self, name, chain):
        """
        Allows to snapshot a chain and save a json file with all chainshot info

        :param chain: the chain object to be snapshot
        :param name: the name (ID) of the snapshot
        :return: a dictionary containing the snapshot info
        """
        results = {
            "chainshot_name": name,
            "instances": []
        }
        for region_instance_pair in chain.instances:
            all_ids = [instance.id for instance in list(region_instance_pair.ec2.instances.all())]
            if region_instance_pair.id not in all_ids:
                raise IndexError("Instance {} not found in region {}".format(region_instance_pair.id,
                                                                             region_instance_pair.region_name))

        halt_ethermint(chain)

        for region_instance_pair in chain.instances:
            instance = region_instance_pair.instance
            volumes_collection = instance.volumes.filter(Filters=[
                {'Name': 'tag-key', 'Values': ["Name"]},
                {'Name': 'tag-value', 'Values': ['ethermint_volume']}
            ])
            volume = list(volumes_collection)[0]

            snapshot_info = self._snapshot(instance, volume, region_instance_pair.ec2)

            results["instances"].append(snapshot_info)

        run_ethermint(chain)

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

        chain = Chain(map(RegionInstancePair.from_boto, instances))
        run_ethermint(chain)

        logger.info("Done starting ethermint on instances")

        return chain
