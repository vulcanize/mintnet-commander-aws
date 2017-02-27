import json
import os
import logging
from os.path import expanduser

from copy import deepcopy

import boto3
import packer

from settings import DEFAULT_REGION, DEFAULT_INSTANCE_TYPE, DEFAULT_AMIS, PACKER_PATH


logger = logging.getLogger()


class AMIBuilder:
    def __init__(self):
        pass

    def _generate_packer_file(self, packer_base_config, ami_name, packer_file_path=expanduser("~"),
                             packer_file_name="salt_packer", region=DEFAULT_REGION):
        """
        Adds a builder to base packer config and saves the file under packer_file_name in packer_file_path
        """
        config = deepcopy(packer_base_config)
        builder = {
            "type": "amazon-ebs",
            "region": region,
            "source_ami": DEFAULT_AMIS[region],
            "instance_type": DEFAULT_INSTANCE_TYPE,
            "ssh_username": "ubuntu",
            "ami_name": ami_name,
        }
        config["builders"].append(builder)

        aws_file = os.path.join(packer_file_path, packer_file_name + '.yml')
        with open(aws_file, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info("Packer file {} saved successfully".format(packer_file_name))
        return aws_file

    def _build_ami_image(self, packer_file, access_key, secret_key):
        """
        Performs packer validate and packer build.
        The result is the AMI of a machine on EC2 which can be used to run more instances
        """
        vars = {
            "aws_access_key": access_key,
            "aws_secret_key": secret_key
        }

        p = packer.Packer(packer_file, vars=vars, exec_path=PACKER_PATH)

        validation_result = p.validate(syntax_only=False)
        if not validation_result.succeeded:
            logger.error("Unable to do packer build, error while validating template: {}".format(validation_result.error))
            return

        build_result = p.build(parallel=True, debug=False, force=False)

        # retrieve the AMI ID from the command output
        s = str(filter(lambda line: line != '', build_result.stdout.split('\n'))[-1])
        ami = s[s.find(":") + 1:-3].strip()
        logger.info("AMI {} created successfully".format(ami))
        return ami

    def _get_credentials(self):
        """
        Reads the AWS credentials from default location
        """
        session = boto3.Session()
        credentials = session.get_credentials()
        access_key = credentials.access_key
        secret_key = credentials.secret_key
        return access_key, secret_key

    def create_ami(self, packer_builder_config, ami_name, packer_file_name):
        """
        Creates an AMI in AWS in DEFAULT_REGION and returns its ID
        """
        packer_file = self._generate_packer_file(packer_builder_config, ami_name, packer_file_name=packer_file_name)
        access_key, secret_key = self._get_credentials()
        return self._build_ami_image(packer_file, access_key, secret_key)
