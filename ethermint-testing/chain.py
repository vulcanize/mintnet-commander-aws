import boto3

from tendermint_app_interface import TendermintAppInterface, EthermintInterface
from utils import get_region_name


class RegionInstancePair:
    """
    Region and ec2-resource bound instance. Picklable, workable as a boto3 Instance instance

    Main reason for this class is being picklable, which in turn is needed by our current parallel processing
    """

    def __init__(self, region_name, instance_id):
        self.region_name = region_name
        self.id = instance_id

        # borrow the properties from the boto3 Instance defined by region/id
        # set new properties on RegionInstancePair class by copying properties from self.instance
        for prop in ['key_name', 'public_ip_address', 'block_device_mappings', 'image_id', 'security_groups',
                     'tags', 'volumes', 'placement']:
            iife = lambda iife_prop: lambda innerself: getattr(innerself.instance, iife_prop)
            setattr(self.__class__, prop, property(iife(prop)))

    @staticmethod
    def from_boto(instance):
        return RegionInstancePair(get_region_name(instance.placement["AvailabilityZone"]), instance.id)

    @property
    def instance(self):
        """
        use instance.instance to instantiate the instance instance for instance id
        :return:
        """
        return self.ec2.Instance(self.id)

    @property
    def ec2(self):
        return boto3.resource('ec2', region_name=self.region_name)

    @property
    def instance_name(self):
        name = None
        for tag in self.instance.tags:
            if tag["Key"] == "Name":
                name = tag["Value"]
                break
        if not name:
            name = "Node_" + self.instance.id
        return name


class Chain:
    def __init__(self, instances, name="", chain_type="ethermint"):
        self.instances = instances  # a list of RegionInstancePairs
        self.chain_interface = EthermintInterface if chain_type == "ethermint" else TendermintAppInterface
        self.name = name

    @property
    def instance_block_infos(self):
        """
        Returns a list of tuples, where the first parameter is a region instance pair
        and the second is the latest block in that instance
        :return:
        """
        return [(region_instance_pair, self.chain_interface.get_block(region_instance_pair.instance))
                for region_instance_pair in self.instances]

    def __str__(self):
        result = ""
        for instance in self.instances:
            result += "{}:{}\n".format(instance.region_name, instance.id)
        return result

    def serialize(self):
        """
        Chain serialization to JSON
        :return: a dictionary
        """
        result = {
            "instances": [],
            "name": self.name,
            "type": "ethermint" if isinstance(self.chain_interface, EthermintInterface) else "tendermintapp"
        }
        for region_instance_pair in self.instances:
            result["instances"].append(dict(instance={
                "id": region_instance_pair.id,
                "region": region_instance_pair.region_name
            }))
        return result

    @staticmethod
    def deserialize(data):
        """
        Create a new chain instance from dict serialization
        :param data:
        :return: chain object
        """
        assert "instances" in data
        instances = []
        for instance_data in data["instances"]:
            instances.append(RegionInstancePair(instance_data["instance"]["region"],
                                                instance_data["instance"]["id"]))
        return Chain(instances, name=data.get("name", ""), chain_type=data.get("chain_type", "ethermint"))
