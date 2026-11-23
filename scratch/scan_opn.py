import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('41.214.254.0', port=22, username='manager', password='K@plus@2026', timeout=10, look_for_keys=False, allow_agent=False)

cmd = """python3 -c "
import socket
target = '192.168.1.1'
common_ports = [21, 22, 23, 53, 80, 443, 9443, 2222, 2200, 8080, 8443, 1194, 3000, 10000]
open_ports = []
for p in common_ports:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    if s.connect_ex((target, p)) == 0:
        open_ports.append(p)
    s.close()
print('Open TCP ports on 192.168.1.1:', open_ports)
" """

stdin, stdout, stderr = client.exec_command(cmd)
print(stdout.read().decode())
client.close()
