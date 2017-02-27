import json
import os
import logging

import boto3

from commands import command_mount_volume, command_perform_rsync, command_unmount_volume
from settings import DEFAULT_SNAPSHOT_VOLUME_SIZE, DEFAULT_DEVICE, BACKUP_DIRS, DEFAULT_SSH_OPTIONS


logger = logging.getLogger()


class Chainshotter:
    def __init__(self):
        self.ec2 = boto3.resource('ec2')
        self.ec2_client = boto3.client('ec2')

    def _snapshot_to_volume(self, instance, volume_id):
        """
        Based on http://www.takaitra.com/posts/384
        TODO a nicer way of doing this
        :param instance:
        :param volume_id:
        :return:
        """
        volume = self.ec2.Volume(volume_id)
        volume.attach_to_instance(InstanceId=instance.id, Device=DEFAULT_DEVICE)
        logger.info("Volume {} attached to instance {}".format(volume_id, instance.id))

        # wait for volume
        waiter = self.ec2_client.get_waiter('volume_in_use')
        waiter.wait(VolumeIds=[volume_id])

        ssh_params = DEFAULT_SSH_OPTIONS(instance.key_name)

        os.system(command_mount_volume(ssh_params, instance.public_ip_address, DEFAULT_DEVICE))

        logger.info('Beginning rsync')
        for backup_dir in BACKUP_DIRS:
            os.system(command_perform_rsync(ssh_params, instance.public_ip_address, backup_dir))
        logger.info('Rsync complete')

        logger.info('Unmounting and detaching volume {}'.format(volume_id))
        os.system(command_unmount_volume(ssh_params, instance.public_ip_address))
        volume.detach_from_instance(InstanceId=instance.id)

        logger.info('Waiting for volume {} to switch to Available state'.format(volume_id))
        waiter = self.ec2_client.get_waiter('volume_available')
        waiter.wait(VolumeIds=[volume_id])
        logger.info('Volume {} available'.format(volume_id))

    def chainshot(self, name, instances, filename="chainshot_info.json"):
        """
        Allows to snapshot a chain and save a json file with all chainshot info

        :param name: the name (ID) of the snapshot
        :param instances: the list of instances to be snapshotted
        :param filename: the file where the results are saved
        :return:
        """

        results = {
            "chainshot_name": name,
            "instances": []
        }

        for instance in instances:
            volume_info = self.ec2.create_volume(Size=DEFAULT_SNAPSHOT_VOLUME_SIZE,
                                                 # TODO calculate that using the instance
                                                 AvailabilityZone=instance.placement["AvailabilityZone"])
            volume_id = volume_info["VolumeId"]
            logger.info("Volume {} created".format(volume_id))

            self._snapshot_to_volume(instance, volume_id)
            logger.info("Finished snapshotting")

            snapshot_info = {
                "instance_id": instance.id,
                "instace_region": instance.placement["AvailabilityZone"],
                "instance_ami": instance.image_id,
                "instance_tags": instance.tags,
                "instance_vpc_id": instance.vpc_id,
                "instance_security_groups": instance.security_groups,

                "volume_id": volume_id,
                "volume_region": volume_info["AvailabilityZone"],

                # only approximate
                "snapshot_from": instance.created,
                "snapshot_to": volume_info["CreateTime"],
            }
            results[instances].append(snapshot_info)

        logger.info(results)

        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)

    def thaw(self, chainshot, ami):
        pass
