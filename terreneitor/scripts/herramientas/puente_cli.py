#!/usr/bin/env python3
import argparse
import os
import sys

import requests

# CONFIG
BASE_URL = os.environ.get("MONSTRUO_BASE_URL", "http://127.0.0.1:8000")
TOKEN = os.environ.get("MONSTRUO_TOKEN", "")


def send_message(args):
    url = f"{BASE_URL}/api/bridge/messages"
    payload = {
        "kind": args.kind,
        "title": args.title,
        "body": args.body,
        "from_agent": "Terreneitor",
        "to_agent": args.to,
        "payload": args.payload,
    }

    try:
        r = requests.post(url, json=payload)
        r.raise_for_status()
        print(f"✅ Message sent! ID: {r.json()['id']}")
    except Exception as e:
        print(f"❌ Error sending message: {e}")
        sys.exit(1)


def check_inbox(args):
    url = f"{BASE_URL}/api/bridge/inbox"
    params = {"to": "Terreneitor"}
    if args.status:
        params["status"] = args.status

    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        msgs = r.json()

        if not msgs:
            print("📭 Inbox empty.")
            return

        print(f"📬 Inbox ({len(msgs)} messages):")
        for m in msgs:
            print(
                f"[{m['id']}] {m['kind'].upper()}: {m['title']} (from {m['from_agent']}) [{m['status']}]"
            )
            print(f"    {m['body']}")
            if m["payload"]:
                print(f"    Payload: {m['payload']}")
            print("-" * 40)

    except Exception as e:
        print(f"❌ Error checking inbox: {e}")
        sys.exit(1)


def check_pending(args):
    url = f"{BASE_URL}/api/bridge/pending"
    try:
        r = requests.get(url)
        r.raise_for_status()
        msgs = r.json()

        if not msgs:
            print("✅ No pending tasks.")
            return

        print(f"🕒 Pending Tasks ({len(msgs)}):")
        for m in msgs:
            print(f"[{m['id']}] {m['to_agent']}: {m['title']}")
    except Exception as e:
        print(f"❌ Error checking pending: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Terreneitor Bridge CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # SEND
    send_parser = subparsers.add_parser("send", help="Send a message")
    send_parser.add_argument("--to", required=True, help="Recipient agent")
    send_parser.add_argument("--title", required=True, help="Message title")
    send_parser.add_argument("--body", required=True, help="Message body")
    send_parser.add_argument(
        "--kind",
        default="request",
        choices=["request", "proposal", "result"],
        help="Message kind",
    )
    send_parser.add_argument("--payload", help="JSON payload string")
    send_parser.set_defaults(func=send_message)

    # INBOX
    inbox_parser = subparsers.add_parser("inbox", help="Check inbox")
    inbox_parser.add_argument(
        "--status",
        choices=["pending", "approved", "done", "rejected"],
        help="Filter by status",
    )
    inbox_parser.set_defaults(func=check_inbox)

    # PENDING
    pending_parser = subparsers.add_parser("pending", help="Check all pending messages")
    pending_parser.set_defaults(func=check_pending)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
