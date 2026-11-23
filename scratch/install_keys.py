import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('41.214.254.0', port=22, username='manager', password='K@plus@2026', timeout=10, look_for_keys=False, allow_agent=False)

key1 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINAco5OVZxheti6jeN5U+0kYYFm+wurMpsVXmQ812f0P 7mza@DESKTOP-978P3EK"
key2 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHuCWcXbHq9ZVqgAGPvojST9PVqhU1CVtjbGS1CBN+l+ 7mza@DESKTOP-978P3EK"

cmd = f'echo "{key1}" >> /home/manager/.ssh/authorized_keys && echo "{key2}" >> /home/manager/.ssh/authorized_keys && chmod 600 /home/manager/.ssh/authorized_keys'
stdin, stdout, stderr = client.exec_command(cmd)
err = stderr.read().decode()
if err:
    print("Error:", err)
else:
    print("Successfully added Hamza's SSH keys to authorized_keys on prod VPS!")

stdin, stdout, stderr = client.exec_command("cat /home/manager/.ssh/authorized_keys")
print(stdout.read().decode())
client.close()
