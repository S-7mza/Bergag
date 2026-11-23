import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
# Connect to jump host
client.connect('41.214.254.0', port=22, username='manager', password='K@plus@2026', timeout=10, look_for_keys=False, allow_agent=False)

# Tunnel to 192.168.1.3
trans = client.get_transport()
chan = trans.open_channel('direct-tcpip', ('192.168.1.3', 22), ('127.0.0.1', 0))

target = paramiko.SSHClient()
target.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    target.connect('192.168.1.3', port=22, username='manager', password='123', sock=chan, timeout=10, look_for_keys=False, allow_agent=False)
    print("SUCCESS! Connected to 192.168.1.3 with manager / 123!")
    stdin, stdout, stderr = target.exec_command("hostname; whoami; pwd; docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'")
    print(stdout.read().decode())
    target.close()
except Exception as e:
    print("Failed to connect:", e)

client.close()
