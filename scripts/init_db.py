#!/usr/bin/env python3
"""Create the schema and provision the local workspace in one shot.

Run this once against a new database -- typically the Neon instance behind a
Vercel deployment, which sets ``AUTO_INIT_DB=false`` and therefore does no
schema work at startup:

    DATABASE_URL="postgresql://...?sslmode=require" python scripts/init_db.py

The operation is idempotent: tables are created if missing, additive columns are
added if an older revision lacks them, and the implicit workspace is provisioned
only when it does not exist yet.
"""
import logging
import os
import sys

# The script lives in scripts/, so the import root is its parent directory.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.config import settings as app_settings  # noqa: E402
from app.db import (  # noqa: E402
    DATABASE_URL,
    _describe_database_url,
    direct_engine,
    init_db,
)
from app.main import _bootstrap_database  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("init_db")


def main() -> int:
    print(f"Database: {_describe_database_url(DATABASE_URL)}")
    if not DATABASE_URL or DATABASE_URL.startswith("sqlite"):
        print(
            "Refusing to initialise an ephemeral SQLite file.\n"
            "Set DATABASE_URL to a real database (Postgres in production).",
            file=sys.stderr,
        )
        return 2

    # DDL runs on the direct endpoint when Neon supplies one. The pooled
    # endpoint multiplexes transactions and cannot be used for migrations.
    target = direct_engine()
    print(
        "Schema engine:",
        _describe_database_url(
            str(target.url.render_as_string(hide_password=True))
        ),
    )

    try:
        init_db(engine_override=target)
    except Exception as exc:
        print(f"Schema creation failed: {exc}", file=sys.stderr)
        return 1

    try:
        _bootstrap_database()
    except Exception as exc:  # provisioning is best-effort, but report it
        print(f"Schema created, but provisioning failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Schema ready and workspace provisioned "
        f"(autopilot={app_settings.DEFAULT_AUTOPILOT})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())