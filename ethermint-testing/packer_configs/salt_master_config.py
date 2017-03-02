packer_salt_master_config = {
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
                "sudo apt-get install -y salt-api salt-master salt-ssh",
                "echo 127.0.0.1 salt | sudo cat >> /etc/hosts",
                "sudo update-rc.d salt-master defaults",
                "sudo ufw allow salt",  # firewall: open ports
                "sudo service salt-master restart",
                "sleep 10",  # let things settle
                "sudo salt-key -A --yes",  # accept all minions TODO only accept our minions
            ]
        },
    ]
}
