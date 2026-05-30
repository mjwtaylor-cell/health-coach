"""Fetch all sources → normalize → write to SQLite. Idempotent; safe to re-run."""
from __future__ import annotations

import sys

import config
from db import init_db, upsert
from sources import apple_health, eightsleep, oura, strava


def run(days_back: int = 30) -> None:
    init_db()
    total = 0

    if config.have_oura():
        try:
            for table, rows in oura.fetch(days_back).items():
                total += upsert(table, rows)
            print("[oura] ok")
        except Exception as exc:
            print(f"[oura] FAILED: {type(exc).__name__}: {exc}")
    else:
        print("[oura] no token — skipped")

    if config.have_strava():
        try:
            for table, rows in strava.fetch(days_back).items():
                total += upsert(table, rows)
            print("[strava] ok")
        except Exception as exc:
            print(f"[strava] FAILED: {type(exc).__name__}: {exc}")
    else:
        print("[strava] no creds — skipped")

    if config.have_eightsleep():
        for table, rows in eightsleep.fetch(days_back).items():
            total += upsert(table, rows)
        print("[eightsleep] done")
    else:
        print("[eightsleep] no creds — skipped")

    if config.have_apple():
        try:
            for table, rows in apple_health.fetch().items():
                total += upsert(table, rows)
            print(f"[apple] ok ({config.APPLE_HEALTH_DIR})")
        except Exception as exc:
            print(f"[apple] FAILED: {type(exc).__name__}: {exc}")
    else:
        print(f"[apple] export dir not found ({config.APPLE_HEALTH_DIR}) — skipped")

    print(f"\nWrote {total} rows.")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    run(days)
