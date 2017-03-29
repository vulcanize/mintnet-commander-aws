clean-go:
  pkg.purged:
    - pkgs:
      - golang-go

golang:
  archive:
    - extracted
    - name: /opt/go/go-1.8.0
    - archive_format: tar
    - source: https://storage.googleapis.com/golang/go1.8.linux-amd64.tar.gz
    - source_hash: sha256=53ab94104ee3923e228a2cb2116e5e462ad3ebaeea06ff04463479d7f12d27ca
    - options: z
    - if_missing: /opt/go/go-1.8.0/go
    - require:
      - file: /opt/go/go-1.8.0

/opt/go/go-1.8.0:
  file.directory:
    - makedirs: True

/usr/local/go:
  file.symlink:
    - target: /opt/go/go-1.8.0/go
    - require:
      - archive: golang

goroot:
  cmd.run:
    - name: echo "GOROOT=/usr/local/go" >> /etc/environment
    - unless: cat /etc/environment | grep "GOROOT"

gopath:
  file.directory:
    - name: /usr/local/src/go
    - makedirs: True
  cmd.run:
    - name: echo "GOPATH=/usr/local/src/go" >> /etc/environment &&
            echo "PATH=$GOROOT/bin:$GOPATH/bin:$PATH" >> /etc/environment
    - unless: cat /etc/environment | grep "GOPATH"
    - require:
      - cmd: goroot


