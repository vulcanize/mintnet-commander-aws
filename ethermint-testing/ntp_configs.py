def server_conf(broadcast_mask="172.31.255.255"):
    return """
# /etc/ntp.conf, configuration for ntpd
driftfile /var/lib/ntp/ntp.drift

# IS THIS NEEDED?
statistics loopstats peerstats clockstats
filegen loopstats file loopstats type day enable
filegen peerstats file peerstats type day enable
filegen clockstats file clockstats type day enable

# IS THIS NEEDED?
restrict -4 default kod notrap nomodify nopeer noquery
restrict -6 default kod notrap nomodify nopeer noquery
restrict 127.0.0.1
restrict ::1

broadcast {}
""".format(broadcast_mask)


def client_conf(server_ip):
    return """
# /etc/ntp.conf, configuration for ntpd
driftfile /var/lib/ntp/ntp.drift
server {}

# IS THIS NEEDED?
restrict -4 default kod notrap nomodify nopeer noquery
restrict -6 default kod notrap nomodify nopeer noquery
restrict 127.0.0.1
restrict ::1
    """.format(server_ip)
