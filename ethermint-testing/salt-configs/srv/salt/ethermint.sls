{%- set USER = "ubuntu" -%}
{%- set ETHERMINT_VERSION = "HEAD" -%}
{%- set SEEDS = "" -%}

format-volume:
  cmd.run:
    - name: mkfs -t ext4 /dev/xvdh
    - onlyif:
      - test -b /dev/xvdh
    - unless:
      - file --special-files /dev/xvdh | grep ext4

/ethermint:
  mount.mounted:
    - device: /dev/xvdh
    - fstype: ext4
    - mkmnt: True
    - opts:
      - defaults
    - require:
      - cmd: format-volume
    - onlyif:
      - test -b /dev/xvdh

go-dependencies:
  pkg.installed:
    - names:
      - git
      - wget
      - curl
 
go-install:
  cmd.run:
    - name: curl -s https://storage.googleapis.com/golang/go1.8.linux-amd64.tar.gz | sudo tar -xzC /usr/local
    - unless: test -x /usr/local/go/bin/
    - require:
      - pkg: go-dependencies

go-profile:
  file.managed:
    - name: /etc/profile.d/golang.sh
    - contents: |
        export GOROOT=/usr/local/go
        export PATH=$GOROOT/bin:$PATH
        export GOPATH=/opt/go
    - require:
      - cmd: go-install

gopath:
  file.directory:
    - name: /opt/go
    - makedirs: true
    - user: {{ USER }}
    - group: {{ USER }}
    - recurse:
      - user
      - group
    - require:
      - file: go-profile

{% for subdir in ('bin', 'pkg', 'src') %}
gopath-subdir-{{ subdir }}:
  file.directory:
    - name: /opt/go/{{ subdir }}
    - user: {{ USER }}
    - group: {{ USER }}
    - require:
      - file: gopath
{% endfor %}

ethermint-dependencies:
  pkg.installed:
    - names:
      - libusb-dev
      - ntp
      - ntpdate

ethermint-get:
  cmd.run:
    - name: go get github.com/tendermint/ethermint/cmd/ethermint
    - user: {{ USER }}
    - unless: test -x /opt/go/bin/ethermint
    - require:
      - file: gopath

ethermint-git-checkout:
  cmd.run:
    - name: git -C /opt/go/src/github.com/tendermint/ethermint checkout {{ ETHERMINT_VERSION }}
    - require:
      - pkg: git
      - cmd: ethermint-get

ethermint-install:
  cmd.run:
    - name: go install -x github.com/tendermint/ethermint/cmd/ethermint
    - user: {{ USER }}
    - unless: test -x /opt/go/bin/ethermint
    - require:
      - file: gopath
      - cmd: ethermint-git-checkout

/ethermint/setup/genesis.json:
  file.copy:
    - source: /opt/go/src/github.com/tendermint/ethermint/docker/genesis.json
    - user: {{ USER }}
    - group: {{ USER }}
    - makedirs: True
    - require:
      - mount: /ethermint

/ethermint/data/keystore:
  file.copy:
    - source: /opt/go/src/github.com/tendermint/ethermint/docker/keystore
    - subdir: True
    - makedirs: True
    - user: {{ USER }}
    - group: {{ USER }}
    - require:
      - mount: /ethermint

run-ethermint:
  cmd.run:
    - name: /opt/go/bin/ethermint --datadir /ethermint/data --rpc --rpcaddr=0.0.0.0 --rpcapi "eth,net,web3,personal" {{ SEEDS }} > /ethermint/data/ethermint.log 2>&1
    - require:
      - file: /ethermint/data/keystore
      - file: /ethermint/setup/genesis.json
      - cmd: ethermint-install

