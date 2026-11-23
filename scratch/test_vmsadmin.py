import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('41.214.254.0', port=22, username='manager', password='K@plus@2026', timeout=10, look_for_keys=False, allow_agent=False)

def run(cmd):
    print(f"=== {cmd} ===")
    stdin, stdout, stderr = client.exec_command(cmd)
    print(stdout.read().decode('utf-8', errors='replace').strip())
    print()

run("ssh -o BatchMode=yes -o StrictHostKeyChecking=no vmsadmin@192.168.1.250 'hostname; whoami; virsh list --all || true' 2>&1")

client.close()
