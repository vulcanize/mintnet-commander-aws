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
            "execute_command": "sudo {{.Path}}",
            "inline": [
                "echo '{{user `master_public_key`}}' >> .ssh/authorized_keys",
            ],
        },
        {
            "type": "shell",
            "execute_command": "sudo {{.Path}}",
            "environment_vars": ["ETHERMINT={}".format(ethermint_version_hash)],
            "inline": [
                "./shell_scripts/setup_salt_ethermint.sh",
            ]
        },
    ]
}
