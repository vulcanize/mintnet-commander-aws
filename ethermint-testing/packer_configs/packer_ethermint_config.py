packer_ethermint_config = {
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
            "scripts": [
                "shell_scripts/setup_salt_ethermint.sh"
            ]
        },
    ]
}
