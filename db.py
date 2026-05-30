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

_turso_conn = None  # reused across Streamlit reruns


def _use_turso() -> bool:
    """Checked LIVE (not at import) — Streamlit Cloud may load secrets after import."""
    return bool(config.secret("TURSO_DATABASE_URL"))

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


def _turso():
    """Reused libsql-client (pure-Python, HTTP transport) for the hosted DB."""
    global _turso_conn
    if _turso_conn is None:
        import libsql_client
        # libsql:// defaults to a websocket transport some endpoints reject; force https.
        url = config.secret("TURSO_DATABASE_URL").replace("libsql://", "https://", 1)
        _turso_conn = libsql_client.create_client_sync(url=url, auth_token=config.secret("TURSO_AUTH_TOKEN"))
    return _turso_conn


def init_db() -> None:
    if _use_turso():
        _turso().batch(list(SCHEMA))
        return
    conn = sqlite3.connect(DB_PATH)
    for stmt in SCHEMA:
        conn.execute(stmt)
    conn.commit()
    conn.close()


def _fetch(sql: str, params: tuple = ()):
    if _use_turso():
        rs = _turso().execute(sql, list(params))
        return list(rs.columns), [tuple(r) for r in rs.rows]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    conn.close()
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
    if _use_turso():
        _turso().batch([(sql, row) for row in data])  # atomic batch
        return len(rows)
    conn = sqlite3.connect(DB_PATH)
    conn.executemany(sql, data)
    conn.commit()
    conn.close()
    return len(rows)


if __name__ == "__main__":
    init_db()
    print(f"Initialized DB ({'Turso' if _use_turso() else DB_PATH})")
