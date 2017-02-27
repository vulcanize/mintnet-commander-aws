command_mount_volume = lambda ssh_settings, ip_address, volume_device: "ssh -t {0} ec2-user@{1} \"sudo mkdir /mnt/data-store && sudo mount {2} /mnt/data-store && echo 'Defaults !requiretty' | sudo tee /etc/sudoers.d/rsync > /dev/null\"".format(ssh_settings, ip_address, volume_device)

command_perform_rsync = lambda ssh_settings, ip_address, backup_directory: "sudo rsync -e \"ssh {0}\" -avz --delete --rsync-path=\"sudo rsync\" {2} ec2-user@{1}:/mnt/data-store{2}".format(ssh_settings, ip_address, backup_directory)

command_unmount_volume = lambda ssh_settings, ip_address: "ssh -t {0} ec2-user@{1} \"sudo umount /mnt/data-store\"".format(ssh_settings, ip_address)
