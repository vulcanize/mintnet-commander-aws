import boto3
import time


def wait_for_detached(volume, instance):
    state = None
    while state != 'detached':
        device = filter(lambda dev: dev["Ebs"]["VolumeId"] == volume.id, instance.block_device_mappings)[0]
        state = device["Ebs"]["Status"]
        time.sleep(3)


def wait_for_available_volume(volume, region):
    if volume.state != 'available':
        ec2_client = boto3.client('ec2', region_name=region)
        volume_waiter = ec2_client.get_waiter('volume_available')
        volume_waiter.wait(VolumeIds=[volume.id])
