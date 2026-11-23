import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('41.214.254.0', port=22, username='manager', password='K@plus@2026', timeout=10, look_for_keys=False, allow_agent=False)

def run(cmd):
    print(f"=== {cmd} ===")
    stdin, stdout, stderr = client.exec_command(cmd)
    print(stdout.read().decode('utf-8', errors='replace').strip())
    print()

run("find /home/manager -name '*vpn*' 2>/dev/null || true")
run("find /home/manager -name '*opnsense*' 2>/dev/null || true")
run("cat /etc/openvpn/server.conf 2>/dev/null || true")
run("ps aux | grep -i vpn || true")

client.close()
