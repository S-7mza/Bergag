#!/usr/bin/env python3
"""
Remote Production Deployment & Command Runner
=============================================
Runs Git pull and Docker container management on the production machine (192.168.1.3)
via the Edge JumpHost (41.214.254.0:22).

Usage:
  python scripts/remote_deploy.py [--user <ssh_user>] [--repo <path>] [--cmd "<command>"]
"""

import sys
import os
import argparse
import getpass
import paramiko

# Console encoding for Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

JUMP_HOST = "41.214.254.0"
JUMP_PORT = 22
JUMP_USER = "manager"
JUMP_PASS = "K@plus@2026"

DEFAULT_TARGET_IP = "192.168.1.3"
DEFAULT_TARGET_PORT = 22
DEFAULT_TARGET_USER = "manager"
DEFAULT_REPO_DIR = "/home/manager/mp"

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def main():
    parser = argparse.ArgumentParser(description="Deploy updates to production via JumpHost")
    parser.add_argument("--user", default=DEFAULT_TARGET_USER, help="SSH user on target server (192.168.1.3)")
    parser.add_argument("--target", default=DEFAULT_TARGET_IP, help="Target server IP (default: 192.168.1.3)")
    parser.add_argument("--repo", default=DEFAULT_REPO_DIR, help="Remote repository path")
    parser.add_argument("--cmd", default="", help="Custom command to run instead of default deploy")
    parser.add_argument("--password", default="", help="Password for target user (if omitted, prompts or uses jump pass)")
    args = parser.parse_args()

    print(f"\n{CYAN}{'=' * 65}{RESET}")
    print(f"{CYAN}{BOLD}  🚀 Bergag Production Remote Deployer{RESET}")
    print(f"{DIM}     Jump Host : {JUMP_USER}@{JUMP_HOST}:{JUMP_PORT}{RESET}")
    print(f"{DIM}     Target    : {args.user}@{args.target}:{DEFAULT_TARGET_PORT}{RESET}")
    print(f"{CYAN}{'=' * 65}{RESET}\n")

    # Step 1: Connect to JumpHost
    print(f"{YELLOW}▶ [1/3] Connecting to Jump Host ({JUMP_USER}@{JUMP_HOST})...{RESET}")
    jump_client = paramiko.SSHClient()
    jump_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        jump_client.connect(
            hostname=JUMP_HOST,
            port=JUMP_PORT,
            username=JUMP_USER,
            password=JUMP_PASS,
            timeout=15,
            look_for_keys=False,
            allow_agent=False
        )
        print(f"{GREEN}✓ Connected to Jump Host successfully!{RESET}\n")
    except Exception as e:
        print(f"{RED}✖ Jump host connection failed: {e}{RESET}")
        sys.exit(1)

    # Step 2: Open tunnel to target
    print(f"{YELLOW}▶ [2/3] Establishing SSH Tunnel to {args.target}:22...{RESET}")
    try:
        transport = jump_client.get_transport()
        channel = transport.open_channel("direct-tcpip", (args.target, DEFAULT_TARGET_PORT), ("127.0.0.1", 0))
    except Exception as e:
        print(f"{RED}✖ Failed to open tunnel through jump host: {e}{RESET}")
        jump_client.close()
        sys.exit(1)

    target_pass = args.password
    if not target_pass:
        target_pass = JUMP_PASS

    target_client = paramiko.SSHClient()
    target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Try connecting with default credentials or ask user
    connected = False
    try:
        target_client.connect(
            hostname=args.target,
            port=DEFAULT_TARGET_PORT,
            username=args.user,
            password=target_pass,
            sock=channel,
            timeout=10,
            look_for_keys=True,
            allow_agent=True
        )
        connected = True
    except paramiko.AuthenticationException:
        print(f"{YELLOW}⚠ Password authentication failed for {args.user}@{args.target}.{RESET}")
        user_entered_pass = getpass.getpass(f"Enter SSH password for {args.user}@{args.target}: ")
        channel = transport.open_channel("direct-tcpip", (args.target, DEFAULT_TARGET_PORT), ("127.0.0.1", 0))
        target_client.connect(
            hostname=args.target,
            port=DEFAULT_TARGET_PORT,
            username=args.user,
            password=user_entered_pass,
            sock=channel,
            timeout=10
        )
        connected = True

    if not connected:
        print(f"{RED}✖ Could not authenticate to {args.user}@{args.target}.{RESET}")
        jump_client.close()
        sys.exit(1)

    print(f"{GREEN}✓ Connected to target server ({args.target})!{RESET}\n")

    # Step 3: Run deployment command
    if args.cmd:
        deploy_cmd = args.cmd
    else:
        deploy_cmd = (
            f"if [ -d '{args.repo}' ]; then cd '{args.repo}' && git pull origin main && "
            f"docker compose up -d --build && docker compose ps; "
            f"else echo 'Listing home directory:'; ls -la ~; docker ps; fi"
        )

    print(f"{YELLOW}▶ [3/3] Executing commands on target server:{RESET}")
    print(f"{DIM}    $ {deploy_cmd}{RESET}\n")

    stdin, stdout, stderr = target_client.exec_command(deploy_cmd, get_pty=True)
    for line in iter(stdout.readline, ""):
        print(line, end="", flush=True)

    err = stderr.read().decode('utf-8', errors='replace').strip()
    if err:
        print(f"\n{YELLOW}[Stderr]:{RESET}\n{err}")

    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        print(f"\n{GREEN}{BOLD}✓ Deployment completed successfully!{RESET}\n")
    else:
        print(f"\n{RED}✖ Command finished with exit code: {exit_status}{RESET}\n")

    target_client.close()
    jump_client.close()


if __name__ == "__main__":
    main()
