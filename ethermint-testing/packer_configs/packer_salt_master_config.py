packer_salt_ssh_master_config = {
    "variables": {
        "aws_access_key": "",
        "aws_secret_key": "",
        "master_public_key": "",
        "master_private_key": ""
    },
    'builders': [],
    'provisioners': [
        {
            "type": "shell",
            "execute_command": "sudo {{.Path}}",
            "inline": [
                "set -x",  # show stuff being executed

                # salt stuff
                "sudo add-apt-repository -y ppa:saltstack/salt",
                "sudo apt-get update",
                "sudo apt-get install -y salt-master salt-ssh",
                "echo '{{user `master_private_key`}}' >> .ssh/master_key",
                "echo '{{user `master_public_key`}}' >> .ssh/master_key.pub",
            ]
        },
    ]
}
