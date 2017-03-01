packer_salt_ssh_minion_config = {
    "variables": {
        "aws_access_key": "",
        "aws_secret_key": ""
    },
    'builders': [],
    'provisioners': [
        {
            "type": "shell",
            "execute_command": "sudo {{.Path}}",
            "inline": [
                "set -x",  # show stuff being executed
                "sleep 30",

                # salt stuff
                "sudo add-apt-repository -y ppa:saltstack/salt",
                "sudo apt-get update",
                "sudo apt-get install -y salt-ssh",
            ]
        },
    ]
}
