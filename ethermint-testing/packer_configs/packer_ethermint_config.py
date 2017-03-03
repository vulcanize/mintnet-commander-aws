packer_ethermint_config = {
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
                "sudo apt-get -y update",
                "sudo apt-get install -y salt-ssh",

                # ethermint stuff
                "sudo apt-get -y update",
                "sudo apt-get install -y git",
                "sudo apt-get install -y golang python",
                "mkdir $HOME/go",
                "export GOPATH=$HOME/go",
                "mkdir -p \"$GOPATH/src\" \"$GOPATH/bin\" && chmod -R 777 \"$GOPATH\"",
                "export PATH=$GOPATH/bin:/usr/local/go/bin:$PATH",
                "curl https://glide.sh/get | sh",

                # TODO
                # "go get github.com/tendermint/ethermint/cmd/ethermint",
                # "go install -x github.com/tendermint/ethermint/vendor/github.com/tendermint/tendermint/cmd/tendermint",
            ]
        },
    ]
}
