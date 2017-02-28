import os
import logging

import boto3
import time

from settings import DEFAULT_PORTS, DEFAULT_REGION, DEFAULT_INSTANCE_TYPE, DEFAULT_INSTANCE_NAME, \
    DEFAULT_SECURITY_GROUP_DESCRIPTION, DEFAULT_SNAPSHOT_VOLUME_SIZE, DEFAULT_DEVICE

logger = logging.getLogger(__name__)


class Chainmaker:
    def __init__(self):
        self.ec2 = boto3.resource('ec2', region_name=DEFAULT_REGION)
        self.ec2_client = boto3.client('ec2')

    def create_security_group(self, name, ports):
        # TODO allow more complex ports definition
        security_group = self.ec2.create_security_group(GroupName=name,
                                                        Description=DEFAULT_SECURITY_GROUP_DESCRIPTION)
        for port in ports:
            security_group.authorize_ingress(IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': port,
                    'ToPort': port,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                },
            ])
        logger.info("Security group {} created".format(name))

    def add_volume(self, instance_id):
        instance = self.ec2.Instance(instance_id)
        volume = self.ec2.create_volume(Size=DEFAULT_SNAPSHOT_VOLUME_SIZE,
                                   AvailabilityZone=instance.placement["AvailabilityZone"])

        assert volume.availability_zone == instance.placement.get("AvailabilityZone")

        volume = self.ec2.Volume(volume.id)
        volume.attach_to_instance(InstanceId=instance.id, Device=DEFAULT_DEVICE)

        # run ./mount_new_volume.sh

    def create(self, ami, number, security_group_name):
        # for now, only the default region and the default names
        instances = []

        for i in range(number):
            timestamp = "salt-instance" + str(int(time.time()))
            keyfile = timestamp + ".pem"
            # allow to ssh into ec2
            # TODO specify full filepath as a parameter to this function
            key = self.ec2.create_key_pair(KeyName=timestamp)
            with open(keyfile, 'w') as f:
                f.write(key.key_material)
            os.chmod(keyfile, 0o600)

            # create instances returns a list of instances, we want the first element
            instance = self.ec2.create_instances(ImageId=ami,
                                                 InstanceType=DEFAULT_INSTANCE_TYPE,
                                                 MinCount=1,
                                                 MaxCount=1,
                                                 SecurityGroupIds=[security_group_name],
                                                 KeyName=timestamp)[0]
            instance.create_tags(Tags=[
                {
                    'Key': 'Name',
                    'Value': DEFAULT_INSTANCE_NAME + str(i)
                },
            ])
            instance.wait_until_running()
            instances.append(instance)

            logger.info("Created instance with ID {}".format(instance.id))

        # logging.info("Waiting for instances to initialize properly")
        # # wait for instances to initialize properly
        # pending_instances = list(self.ec2.instances.filter(
        #     Filters=[{'Name': 'instance-state-name', 'Values': ['pending']}]))
        # waiter = self.ec2_client.get_waiter('instance_running')
        # waiter.wait(InstanceIds=pending_instances)
        # for instance in instances:
        #     instance.reload()
        #     logging.info('Instance {0} is running, public IP: {1}'.format(instance.id, instance.public_ip_address))
        logger.info("All instances running")

        return instances

    @staticmethod
    def from_json(config):
        """
        Runs an Ec2 instance based on it's config and returns the instance object
        :param config: the config containing the following fields:
        "id", "region", "ami", "tags", "vpc_id", "security_groups", "key_name",
        :return:
        """
        pass
