import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('41.214.254.0', port=22, username='manager', password='K@plus@2026', timeout=10, look_for_keys=False, allow_agent=False)

cmd = """python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
try:
    req = urllib.request.urlopen('http://192.168.1.1', context=ctx, timeout=5)
    print('HTTP Code:', req.getcode())
    print('Final URL:', req.geturl())
except Exception as e:
    print('Request error:', e)
" """

stdin, stdout, stderr = client.exec_command(cmd)
print(stdout.read().decode())
client.close()
