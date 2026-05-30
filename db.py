"""Storage layer. Backend-agnostic: local SQLite by default, or hosted Turso
(libSQL) when TURSO_DATABASE_URL is set — same SQL either way.

All access goes through query() / query_df() / upsert() so callers never touch a
raw connection or a backend-specific row type.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable

import config
from config import DB_PATH

_USE_TURSO = bool(config.TURSO_DATABASE_URL)
_turso_conn = None  # reused across Streamlit reruns

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS sleep (
        date TEXT NOT NULL, source TEXT NOT NULL,
        total_min REAL, deep_min REAL, rem_min REAL, light_min REAL, awake_min REAL,
        efficiency REAL, latency_min REAL,
        hr_avg REAL, hr_low REAL, hrv_avg REAL, temp_dev REAL, spo2 REAL,
        PRIMARY KEY (date, source))""",
    """CREATE TABLE IF NOT EXISTS readiness (
        date TEXT NOT NULL, source TEXT NOT NULL,
        score REAL, hrv_balance REAL, rhr REAL, temp_dev REAL, recovery_index REAL,
        PRIMARY KEY (date, source))""",
    """CREATE TABLE IF NOT EXISTS activity_daily (
        date TEXT NOT NULL, source TEXT NOT NULL,
        steps REAL, active_kcal REAL, total_kcal REAL,
        exercise_min REAL, stand_hours REAL, score REAL,
        PRIMARY KEY (date, source))""",
    """CREATE TABLE IF NOT EXISTS workouts (
        workout_id TEXT PRIMARY KEY, date TEXT NOT NULL, source TEXT NOT NULL,
        type TEXT, start_ts TEXT, duration_min REAL,
        active_kcal REAL, distance_km REAL, hr_avg REAL, hr_max REAL)""",
    """CREATE TABLE IF NOT EXISTS body (
        date TEXT NOT NULL, source TEXT NOT NULL,
        weight_kg REAL, body_fat_pct REAL, vo2max REAL,
        PRIMARY KEY (date, source))""",
    """CREATE TABLE IF NOT EXISTS checkins (
        date TEXT PRIMARY KEY,
        est_calories REAL, protein_g REAL, alcohol_units REAL,
        hunger INTEGER, notes TEXT)""",
    """CREATE TABLE IF NOT EXISTS plans (
        date TEXT PRIMARY KEY, training_call TEXT, session TEXT,
        calorie_target REAL, protein_target REAL, rationale TEXT, created_ts TEXT)""",
]


def _connect():
    """Return a live connection. Turso connection is a reused singleton; SQLite is per-call."""
    global _turso_conn
    if _USE_TURSO:
        if _turso_conn is None:
            import libsql_experimental as libsql
            _turso_conn = libsql.connect(
                database=config.TURSO_DATABASE_URL, auth_token=config.TURSO_AUTH_TOKEN
            )
        return _turso_conn
    return sqlite3.connect(DB_PATH)


def _close(conn) -> None:
    if not _USE_TURSO:
        conn.close()


def init_db() -> None:
    conn = _connect()
    for stmt in SCHEMA:
        conn.execute(stmt)
    conn.commit()
    _close(conn)


def _fetch(sql: str, params: tuple = ()):
    conn = _connect()
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    _close(conn)
    return cols, rows


def query(sql: str, params: tuple = ()) -> list[dict]:
    cols, rows = _fetch(sql, params)
    return [dict(zip(cols, r)) for r in rows]


def query_df(sql: str):
    import pandas as pd
    cols, rows = _fetch(sql)
    return pd.DataFrame(rows, columns=cols)  # keeps columns even when empty


def upsert(table: str, rows: Iterable[dict[str, Any]]) -> int:
    rows = [r for r in rows if r]
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in cols)
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    data = [[r.get(c) for c in cols] for r in rows]
    conn = _connect()
    if _USE_TURSO:
        for row in data:
            conn.execute(sql, row)
    else:
        conn.executemany(sql, data)
    conn.commit()
    _close(conn)
    return len(rows)


if __name__ == "__main__":
    init_db()
    print(f"Initialized DB ({'Turso' if _USE_TURSO else DB_PATH})")
