"""Create or re-password the single admin account.

Admin access on this service is *not* a separate credential: it is a normal account
whose email appears in ``ADMIN_EMAILS``. So "set the admin password" means creating
or updating that user record, using the same PBKDF2 hashing as every other signup.

Run this **on the host**, once, with the same ``DATA_DIR`` the service uses:

    python scripts/provision_admin.py --email superpkay@gmail.com
    python scripts/provision_admin.py --email superpkay@gmail.com --reset   # new password

With ``--reset`` it takes the new password on stdin rather than a command-line
argument, so it never lands in the shell history or in ``ps``. It also forces
``ADMIN_EMAILS`` to exactly that one address, which is what retires any previous
administrator.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path(__file__).parent))

import _data_dir

from orchestrator.auth import hash_password

MIN_PASSWORD_LENGTH = 12


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        for key in ("users", "data", "items"):
            if isinstance(raw.get(key), list):
                return list(raw[key])
        return [raw]
    return list(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="The one admin address.")
    parser.add_argument("--name", default="Pkay Admin", help="Display name for a new record.")
    parser.add_argument("--data-dir", default=None, help="Overrides DATA_DIR.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Set a new password even if the account exists.",
    )
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation.")
    args = parser.parse_args()

    email = args.email.strip().lower()

    data_dir = args.data_dir
    if not data_dir:
        try:
            from shared.config import get_settings

            data_dir = get_settings().data_dir
        except Exception:  # pragma: no cover - operator convenience
            data_dir = None

    base = _data_dir.resolve(data_dir)
    _data_dir.assert_present(base)

    users_path = base / "users.json"
    users = load(users_path)
    existing = next((u for u in users if str(u.get("email", "")).lower() == email), None)

    if existing and not args.reset:
        print(f"{email} already exists (plan={existing.get('plan')}).")
        print("Re-run with --reset to set a new password.")
    else:
        print(f"Enter the password for {email} (min {MIN_PASSWORD_LENGTH} chars).")
        password = getpass.getpass("  password: ")
        confirm = getpass.getpass("  confirm : ")
        if password != confirm:
            print("Passwords did not match.", file=sys.stderr)
            return 1
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
            return 1

        encoded = hash_password(password, salt=secrets.token_bytes(16))
        now = datetime.now(UTC).isoformat()

        if existing:
            existing["password_hash"] = encoded
            existing["verified"] = True
            record = existing
            action = "password reset"
        else:
            record = {
                "id": secrets.token_hex(16),
                "name": args.name,
                "email": email,
                "password_hash": encoded,
                "created_at": now,
                "provider": "password",
                "subject": None,
                "verified": True,
                "plan": "free",
                "plan_expires_at": None,
                "analysis_used": 0,
                "analysis_period_start": now,
                "analysis_used_today": 0,
                "analysis_day_start": now,
            }
            users.append(record)
            action = "account created"

        print(f"\n{action} for {email} (id={record['id']}).")

    if not args.yes:
        answer = input(f"Rewrite {users_path}? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted.")
            return 1

    if not users_path.exists():
        print(f"\n{users_path} does not exist; nothing to do.", file=sys.stderr)
        return 1

    temp = users_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(users, indent=2, default=str), encoding="utf-8")
    temp.replace(users_path)
    print(f"Wrote {users_path}")

    print("\nNow retire the old administrators. In the service environment set:")
    print(f'  ADMIN_EMAILS={email}')
    print(
        "The code default is already this address, so an unset ADMIN_EMAILS is "
        "correct; remove any inherited value listing the previous admins."
    )
    print("\nRestart the API, then sign in at /login with these credentials.")
    print("The admin console is at /pkay-control-x7q9 — there is no /admin route.")
    return 0


if __name__ == "__main__":
    if os.name == "nt":  # getpass writes the prompt to stdout on Windows
        pass
    raise SystemExit(main())
