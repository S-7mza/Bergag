import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('41.214.254.0', port=22, username='manager', password='K@plus@2026', timeout=10, look_for_keys=False, allow_agent=False)

trans = client.get_transport()
chan = trans.open_channel('direct-tcpip', ('192.168.1.3', 22), ('127.0.0.1', 0))

target = paramiko.SSHClient()
target.set_missing_host_key_policy(paramiko.AutoAddPolicy())
target.connect('192.168.1.3', port=22, username='manager', password='123', sock=chan, timeout=10, look_for_keys=False, allow_agent=False)

key1 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINAco5OVZxheti6jeN5U+0kYYFm+wurMpsVXmQ812f0P 7mza@DESKTOP-978P3EK"
key2 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHuCWcXbHq9ZVqgAGPvojST9PVqhU1CVtjbGS1CBN+l+ 7mza@DESKTOP-978P3EK"

cmd = f'mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo "{key1}" >> ~/.ssh/authorized_keys && echo "{key2}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
stdin, stdout, stderr = target.exec_command(cmd)
err = stderr.read().decode()
if err:
    print("Error:", err)
else:
    print("SUCCESS: Injected Hamza SSH keys into 192.168.1.3!")

stdin, stdout, stderr = target.exec_command("cat ~/.ssh/authorized_keys")
print(stdout.read().decode())

target.close()
client.close()
