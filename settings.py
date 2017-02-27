# the list of ports to be added to the security group
DEFAULT_PORTS = [22, 4505, 4506]

# the default AWS region
DEFAULT_REGION = "us-east-1"

DEFAULT_INSTANCE_TYPE = "t2.micro"

DEFAULT_INSTANCE_NAME = "test-ethermint-"

DEFAULT_SECURITY_GROUP_DESCRIPTION = 'ethermint-network'

DEFAULT_AMIS = {
    "ap-northeast-1":  "ami-50eaed51",
    "ap-southeast-1":  "ami-f95875ab",
    "eu-central-1":    "ami-ac1524b1",
    "eu-west-1":       "ami-823686f5",
    "sa-east-1":       "ami-c770c1da",
    "us-east-1":       "ami-4ae27e22",
    "us-west-1":       "ami-d1180894",
    "cn-north-1":      "ami-fe7ae8c7",
    "us-gov-west-1":   "ami-cf5630ec",
    "ap-southeast-2":  "ami-890b62b3",
    "us-west-2":       "ami-898dd9b9",
}

PACKER_PATH = "/home/agnieszka/bin/packer"

# the default size of the volume to be used to snapshot a single ec2
DEFAULT_SNAPSHOT_VOLUME_SIZE = 10  # Gb

# defines where to mount volume in ec2
DEFAULT_DEVICE = '/dev/sdh'

# the list of directories which are to be snapshotted
BACKUP_DIRS = ['/home/ubuntu/go']

# TODO!
DEFAULT_SSH_OPTIONS = lambda keyname: '-o StrictHostKeyChecking=no -i ~/{}.pem'.format(keyname)
