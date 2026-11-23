import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('41.214.254.0', port=22, username='manager', password='K@plus@2026', timeout=10, look_for_keys=False, allow_agent=False)

stdin, stdout, stderr = client.exec_command("cat /home/manager/.ssh/authorized_keys")
print("Current authorized_keys on prod:\n", stdout.read().decode())
client.close()
