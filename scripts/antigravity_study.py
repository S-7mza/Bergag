#!/usr/bin/env python3
"""
Antigravity Local AI Study CLI (Zero External LLM Cost)
=======================================================
Exports pending active avis (with line items, CPS excerpts, and Y/Z market context)
from local or production Bergag API, and pushes Antigravity's structured diagnoses back.

Usage:
  python scripts/antigravity_study.py export --limit 20 --out pending_avis.json
  python scripts/antigravity_study.py apply --file studied_avis.json
"""
import argparse
import getpass
import json
import sys
from pathlib import Path

import httpx


def _login(client: httpx.Client, base_url: str, username: str, password: str) -> str:
    res = client.post(
        f"{base_url}/api/auth/login",
        json={"username_or_email": username, "password": password},
    )
    if res.status_code != 200:
        print(f"Login failed ({res.status_code}): {res.text}", file=sys.stderr)
        sys.exit(1)
    return res.json()["token"]


def cmd_export(args):
    base_url = args.url.rstrip("/")
    password = args.password or getpass.getpass(f"Password for {args.username}: ")
    with httpx.Client(timeout=60.0) as client:
        token = _login(client, base_url, args.username, password)
        res = client.get(
            f"{base_url}/api/agent/antigravity/pending",
            params={
                "limit": args.limit,
                "include_studied": str(args.include_studied).lower(),
                "fetch_attachments": str(args.fetch_attachments).lower(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        res.raise_for_status()
        data = res.json()

    out_path = Path(args.out)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {data.get('count', 0)} pending avis to {out_path} (already studied: {data.get('already_studied_total', 0)}).")


def cmd_apply(args):
    base_url = args.url.rstrip("/")
    in_path = Path(args.file)
    raw = json.loads(in_path.read_text(encoding="utf-8"))
    studies = raw["studies"] if isinstance(raw, dict) and "studies" in raw else raw
    if not isinstance(studies, list):
        print("Expected a JSON list of studies or {'studies': [...]}.", file=sys.stderr)
        sys.exit(1)

    password = args.password or getpass.getpass(f"Password for {args.username}: ")
    with httpx.Client(timeout=60.0) as client:
        token = _login(client, base_url, args.username, password)
        res = client.post(
            f"{base_url}/api/agent/antigravity/batch-update",
            json={"studies": studies},
            headers={"Authorization": f"Bearer {token}"},
        )
        res.raise_for_status()
        data = res.json()

    print(f"Successfully updated {data.get('updated_count', 0)} Antigravity studies on {base_url}.")


def main():
    parser = argparse.ArgumentParser(description="Antigravity Local AI Study CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("export", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--url", default="https://bergag.nexenflow.com", help="Bergag base URL")
        p.add_argument("--username", default="hamza", help="Username or email")
        p.add_argument("--password", default=None, help="Password (prompts if omitted)")
        if name == "export":
            p.add_argument("--limit", type=int, default=20)
            p.add_argument("--include-studied", action="store_true")
            p.add_argument("--fetch-attachments", action="store_true")
            p.add_argument("--out", default="pending_avis.json")
        else:
            p.add_argument("--file", required=True, help="JSON file of studied avis")

    args = parser.parse_args()
    if args.command == "export":
        cmd_export(args)
    else:
        cmd_apply(args)


if __name__ == "__main__":
    main()
