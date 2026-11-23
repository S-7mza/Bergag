import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('41.214.254.0', port=22, username='manager', password='K@plus@2026', timeout=10, look_for_keys=False, allow_agent=False)

trans = client.get_transport()
chan = trans.open_channel('direct-tcpip', ('192.168.1.3', 22), ('127.0.0.1', 0))

target = paramiko.SSHClient()
target.set_missing_host_key_policy(paramiko.AutoAddPolicy())
target.connect('192.168.1.3', port=22, username='manager', password='123', sock=chan, timeout=10, look_for_keys=False, allow_agent=False)

def run(cmd):
    print(f"=== {cmd} ===")
    stdin, stdout, stderr = target.exec_command(cmd)
    print(stdout.read().decode('utf-8', errors='replace').strip())
    print()

run("cd /opt/bergag && pwd && git status && git remote -v")
run("cd /opt/bergag && docker compose ps")

target.close()
client.close()
