"""Shorten free-Pro access from two months to one week.

Run this **on the host**, against the live ``DATA_DIR``, after deploying the code
change. It edits ``users.json`` in place, so it takes a timestamped backup first and
refuses to write unless asked twice.

    python scripts/migrate_trial_pro_to_one_week.py --dry-run    # show, change nothing
    python scripts/migrate_trial_pro_to_one_week.py --apply

Who is affected
---------------
Only accounts that hold ``plan == "pro"`` **and** have no billing record with
``status == "paid"``. A user who actually paid has a paid record and is left
completely alone, keeping the 30 days they bought. Trial and manually-granted
accounts have no paid record and are the ones being shortened.

The new expiry is ``min(existing_expiry, now + 7 days)`` rather than a flat
``now + 7 days``: someone whose trial was about to lapse is never *extended* by this
migration, only ever shortened.

Nothing here reads or writes passwords. Enforced plans are not touched either: the
running service already demotes an expired paid plan on the next request
(``plans.enforce``), so shortening the expiry is sufficient.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _data_dir

TRIAL_DAYS = 7
PAID_STATUS = "paid"


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        # Stores have written both a bare list and a mapping wrapper over time.
        for key in ("users", "data", "items"):
            if isinstance(raw.get(key), list):
                return list(raw[key])
        return [raw]
    return list(raw)


def _paid_user_ids(payments: list[dict]) -> set[str]:
    return {
        str(p.get("user_id"))
        for p in payments
        if str(p.get("status")) == PAID_STATUS and p.get("user_id")
    }


def plan_migration(
    users: list[dict],
    payments: list[dict],
    *,
    now: datetime,
    trial_days: int = TRIAL_DAYS,
) -> tuple[list[dict], list[dict]]:
    """Return ``(changed_users, skipped)`` without mutating the inputs."""
    paid = _paid_user_ids(payments)
    ceiling = now + timedelta(days=trial_days)
    changed: list[dict] = []
    skipped: list[dict] = []

    for user in users:
        if str(user.get("plan")) != "pro":
            continue
        user_id = str(user.get("id", ""))
        email = user.get("email", "")

        if user_id in paid:
            skipped.append({"id": user_id, "email": email, "why": "paid"})
            continue

        raw_expiry = user.get("plan_expires_at")
        if not raw_expiry:
            skipped.append({"id": user_id, "email": email, "why": "no expiry set"})
            continue

        try:
            existing = datetime.fromisoformat(str(raw_expiry))
        except ValueError:
            skipped.append({"id": user_id, "email": email, "why": "unparseable expiry"})
            continue

        if existing.tzinfo is None:
            existing = existing.replace(tzinfo=UTC)

        if existing <= now:
            # Already lapsed; the service will demote it on the next request.
            skipped.append({"id": user_id, "email": email, "why": "already expired"})
            continue

        new_expiry = min(existing, ceiling)
        if new_expiry == existing:
            skipped.append({"id": user_id, "email": email, "why": "already within 7 days"})
            continue

        updated = dict(user)
        updated["plan_expires_at"] = new_expiry.isoformat()
        changed.append(
            {
                "id": user_id,
                "email": email,
                "from": existing.isoformat(),
                "to": new_expiry.isoformat(),
                "record": updated,
            }
        )

    return changed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=None, help="Overrides DATA_DIR.")
    parser.add_argument("--dry-run", action="store_true", help="Report only.")
    parser.add_argument("--apply", action="store_true", help="Actually write.")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation.")
    args = parser.parse_args()

    if args.dry_run == args.apply:
        parser.error("choose exactly one of --dry-run or --apply")

    data_dir = args.data_dir
    if not data_dir:
        try:
            from shared.config import get_settings

            sys.path.insert(0, str(Path.cwd()))
            data_dir = get_settings().data_dir
        except Exception:  # pragma: no cover - operator convenience
            data_dir = None

    base = _data_dir.resolve(data_dir)
    _data_dir.assert_present(base)

    users_path = base / "users.json"
    payments_path = base / "billing_payments.json"

    users = _load(users_path)
    payments = _load(payments_path)
    now = datetime.now(UTC)

    changed, skipped = plan_migration(users, payments, now=now)

    print(f"data dir      : {base}")
    print(f"users loaded  : {len(users)}")
    print(f"payments      : {len(payments)}")
    print(f"would shorten : {len(changed)}")
    print(f"left alone    : {len(skipped)}")
    print()

    for row in changed:
        print(f"  SHORTEN {row['email'] or row['id']}")
        print(f"          {row['from']}  ->  {row['to']}")
    for row in skipped:
        print(f"  keep    {row['email'] or row['id']}  ({row['why']})")

    if not args.apply:
        print("\nDry run. Nothing written. Re-run with --apply to make it stick.")
        return 0

    if not args.yes:
        answer = input(f"\nRewrite {users_path} with {len(changed)} change(s)? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted.")
            return 1

    if not users_path.exists():
        print(f"\n{users_path} does not exist; nothing to do.", file=sys.stderr)
        return 1

    backup = users_path.with_suffix(f".json.bak-{now:%Y%m%dT%H%M%SZ}")
    shutil.copy2(users_path, backup)
    print(f"\nBackup written: {backup}")

    by_id = {row["id"]: row["record"] for row in changed}
    rewritten = [by_id.get(str(u.get("id", "")), u) for u in users]

    # Write to a sibling then replace, so an interrupted run cannot truncate the file.
    temp = users_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(rewritten, indent=2, default=str), encoding="utf-8")
    temp.replace(users_path)
    print(f"Wrote {users_path}")
    print("Restart the API so it reloads users.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
