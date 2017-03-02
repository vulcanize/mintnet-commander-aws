packer_salt_minion_config = lambda master_ip: {
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
                "set -x",
                "sleep 30",

                # salt stuff
                "sudo add-apt-repository -y ppa:saltstack/salt",
                "sudo apt-get update",
                "sudo apt-get install -y salt-minion salt-ssh",
                "sudo update-rc.d salt-minion defaults",
                "sudo echo 'master: {}\n' > /etc/salt/minion".format(master_ip),
                "sudo service salt-minion restart",

                # ethermint stuff
                "sudo apt-get update",
                "sudo apt-get upgrade",  # for libperl-error
                "sudo apt-get install -y git",
                "sudo apt-get install -y golang",
                "export GOPATH=$HOME/go",
                "go get github.com/tendermint/ethermint/cmd/ethermint",
            ]
        },
    ]
}
