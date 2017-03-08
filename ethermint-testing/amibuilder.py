import json
import logging
import os
import re
from copy import deepcopy

import boto3
import packer
import sys
from sh import ErrorReturnCode

from settings import DEFAULT_REGION, DEFAULT_INSTANCE_TYPE, DEFAULT_AMIS, PACKER_EXECUTABLE, DEFAULT_FILES_LOCATION

logger = logging.getLogger(__name__)


class AMIBuilder:
    # FIXME different regions
    def __init__(self, master_pub_key, master_priv_key, packer_file_path=DEFAULT_FILES_LOCATION,
                 packer_file_name="salt_packer"):
        access_key, secret_key = self._get_credentials()
        packer_vars = {
            "aws_access_key": access_key,
            "aws_secret_key": secret_key,
            "master_public_key": master_pub_key,
            "master_private_key": master_priv_key
        }
        if not os.path.exists(packer_file_path):
            os.makedirs(packer_file_path)
        self.packer_file_path = os.path.join(packer_file_path, packer_file_name + '.yml')
        open(self.packer_file_path, 'a').close()  # creates an empty file
        self.packer = packer.Packer(self.packer_file_path, vars=packer_vars, exec_path=PACKER_EXECUTABLE)

    def _generate_packer_file(self, packer_base_config, ami_name, region=DEFAULT_REGION):
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

        with open(self.packer_file_path, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info("Packer file {} saved successfully".format(self.packer_file_path))

    def _build_ami_image(self):
        """
        Performs packer validate and packer build.
        The result is the AMI of a machine on EC2 which can be used to run more instances
        """
        validation_result = self.packer.validate(syntax_only=False)
        if not validation_result.succeeded:
            logger.error("Unable to do packer build, "
                         "error while validating template: {}".format(validation_result.error))
            return

        try:
            build_result = self.packer.build(parallel=False, debug=False, force=False)
        except ErrorReturnCode as err:
            logger.error(err.stdout)
            sys.exit(1)

        # retrieve the AMI ID from the command output
        s = str(filter(lambda line: line.strip(), build_result.stdout.split('\n'))[-1])
        ami = re.findall('ami-\w{8}', s)[0]
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

    def create_ami(self, packer_builder_config, ami_name):
        """
        Creates an AMI in AWS in DEFAULT_REGION and returns its ID
        """
        self._generate_packer_file(packer_builder_config, ami_name)
        return self._build_ami_image()
