import os

import boto3
import time

from settings import DEFAULT_PORTS, DEFAULT_REGION, DEFAULT_INSTANCE_TYPE, DEFAULT_INSTANCE_NAME, \
    DEFAULT_SECURITY_GROUP_DESCRIPTION


class Chainmaker:
    def __init__(self):
        self.ec2 = boto3.resource('ec2')
        self.ec2_client = boto3.client('ec2')

    def _create_security_group(self, name, ports):
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

    def create(self, ami, number):
        # for now, only the default region and the default names
        security_group_name = "ethermint-security_group"
        self._create_security_group(security_group_name, DEFAULT_PORTS)

        instances = []

        for i in range(number):
            # this is here to allow different regions in the future
            ec2res = boto3.resource('ec2', region_name=DEFAULT_REGION)

            timestamp = "salt-instance" + str(int(time.time()))
            keyfile = timestamp + ".pem"
            # allow to ssh into ec2
            # TODO specify full filepath as a parameter to this function
            key = self.ec2.create_key_pair(KeyName=timestamp)
            with open(keyfile, 'w') as f:
                f.write(key.key_material)
            os.chmod(keyfile, 0o600)

            # create instances returns a list of instances, we want the first element
            instance = ec2res.create_instances(ImageId=ami,
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
            instances.append(instance)

        # wait for instances to initialize properly
        pending_instances = list(self.ec2.instances.filter(
            Filters=[{'Name': 'instance-state-name', 'Values': ['pending']}]))
        waiter = self.ec2_client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance.id for instance in pending_instances])
        for instance in instances:
            instance.reload()
            print('Instance {0} is running, public IP: {1}'.format(instance.id , instance.public_ip_address))

        return instances
