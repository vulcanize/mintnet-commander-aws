# the list of ports to be added to the security group
import os

# ssh is 22, 4505 and 4506 are needed by salt; 123 is used by ntp, others are ethermint ports
import datetime

DEFAULT_PORTS = [(22, 'tcp'), (4505, 'tcp'), (4506, 'tcp')] + [(46656, 'tcp'), (46657, 'tcp'), (8545, 'tcp')] + \
                [(123, 'udp')]

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

PACKER_EXECUTABLE = "packer"

# the default size of the volume to be used to snapshot a single ec2
DEFAULT_SNAPSHOT_VOLUME_SIZE = 10  # Gb

# defines where to mount volume in ec2 by default
DEFAULT_DEVICE = '/dev/sdh'

# the directory where .pem files and packer config files are kept and created to
DEFAULT_FILES_LOCATION = os.path.join(os.getcwd(), "files")

# how many times to try when connecting to an instance using SSH
MAX_MACHINE_CALL_TRIES = 5

# how much time difference can there be between multiple nodes for a certain block to consider the nodes as in sync
DEFAULT_LIVENESS_THRESHOLD = datetime.timedelta(seconds=10)
