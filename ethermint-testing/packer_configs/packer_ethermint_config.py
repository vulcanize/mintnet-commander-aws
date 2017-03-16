packer_ethermint_config = lambda ethermint_version_hash: {
    "variables": {
        "aws_access_key": "",
        "aws_secret_key": "",
        "master_public_key": ""
    },
    'builders': [],
    'provisioners': [
        {
            "type": "shell",
            "inline": [
                "echo '{{user `master_public_key`}}' >> .ssh/authorized_keys",
            ],
        },
        {
            "type": "shell",
            "environment_vars": ["ETHERMINT={}".format(ethermint_version_hash)],
            "script": "shell_scripts/setup_salt_ethermint.sh",
        },
    ]
}
