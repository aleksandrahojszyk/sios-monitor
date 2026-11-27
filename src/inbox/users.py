from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path
from typing import Optional

from src.sios.config import load_settings
from src.sios.storage import Storage

from .accounts import AccountError, AccountRepository


def _read_password(args: argparse.Namespace) -> str:
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != first:
        raise AccountError("Passwords do not match.")
    return first


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.inbox.users",
        description="Manage individual Monitoring Inbox accounts.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="SQLite file (default: sqlite_path from config/collector.yaml)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a user account")
    create.add_argument("username")
    create.add_argument("--display-name", required=True)
    create.add_argument("--password-stdin", action="store_true")

    sub.add_parser("list", help="list accounts")

    reset = sub.add_parser("set-password", help="change a user's password")
    reset.add_argument("username")
    reset.add_argument("--password-stdin", action="store_true")

    deactivate = sub.add_parser(
        "deactivate",
        help="block sign-in and release the user's claimed tasks",
    )
    deactivate.add_argument("username")

    activate = sub.add_parser("activate", help="allow a user to sign in again")
    activate.add_argument("username")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    path = args.db or load_settings().sqlite_path
    storage = Storage(path)
    accounts = AccountRepository(storage.conn)
    try:
        if args.command == "create":
            user = accounts.create_user(
                args.username, args.display_name, _read_password(args)
            )
            print("Created {} ({})".format(user.username, user.display_name))
        elif args.command == "list":
            for user in accounts.list_users():
                print(
                    "{}\t{}\t{}".format(
                        user.username,
                        user.display_name,
                        "active" if user.is_active else "inactive",
                    )
                )
        elif args.command == "set-password":
            accounts.set_password(args.username, _read_password(args))
            print("Password updated for {}".format(args.username))
        elif args.command == "deactivate":
            accounts.set_active(args.username, False)
            print("Deactivated {}".format(args.username))
        elif args.command == "activate":
            accounts.set_active(args.username, True)
            print("Activated {}".format(args.username))
    except AccountError as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        storage.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
