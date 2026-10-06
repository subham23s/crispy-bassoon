"""Provision an administrator in the configured repository.

Credentials are supplied through environment variables or arguments and are
never written to project files. This command is intentionally separate from
public registration.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.auth.service import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Infrastructure  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", ""))
    args = parser.parse_args()
    if not args.email or not args.password:
        parser.error("provide --email/--password or ADMIN_EMAIL/ADMIN_PASSWORD")
    if len(args.password) < 10:
        parser.error("administrator password must contain at least 10 characters")
    infrastructure = Infrastructure(settings)
    try:
        existing = infrastructure.repository.get_user_by_email(args.email)
        if existing is not None:
            raise SystemExit("an account with that email already exists")
        user = infrastructure.repository.create_user(str(uuid.uuid4()), args.email, hash_password(args.password), "ADMIN", datetime.now(timezone.utc).isoformat())
        print({"status": "created", "user": user, "repository": infrastructure.health()["repository_backend"]})
    finally:
        infrastructure.close()


if __name__ == "__main__":
    main()
