"""Central config: paths and credentials.

Secrets resolve from (1) environment variables, then (2) Streamlit secrets
(st.secrets) — so the same code works locally (.env), on a container host
(env vars), and on Streamlit Community Cloud (secrets.toml).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def secret(name: str, default: str = "") -> str:
    """Look up a config value from env first, then Streamlit secrets."""
    val = os.getenv(name)
    if val:
        return val.strip()
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    return default


# DATA_DIR can be redirected to a persistent volume in the cloud via HC_DATA_DIR.
DATA_DIR = Path(os.path.expanduser(secret("HC_DATA_DIR"))) if secret("HC_DATA_DIR") else ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "health.db"

CHECKINS_DIR = ROOT / "checkins"
CHECKINS_DIR.mkdir(exist_ok=True)

PROFILE_PATH = ROOT / "profile.md"

# Turso (hosted SQLite) — when set, the DB layer uses it instead of a local file.
TURSO_DATABASE_URL = secret("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = secret("TURSO_AUTH_TOKEN")

# --- Credentials ---
OURA_TOKEN = secret("OURA_TOKEN")
STRAVA_CLIENT_ID = secret("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = secret("STRAVA_CLIENT_SECRET")
STRAVA_REFRESH_TOKEN = secret("STRAVA_REFRESH_TOKEN")
EIGHTSLEEP_EMAIL = secret("EIGHTSLEEP_EMAIL")
EIGHTSLEEP_PASSWORD = secret("EIGHTSLEEP_PASSWORD")

_apple_dir = os.getenv("APPLE_HEALTH_DIR", "~/Library/Mobile Documents/com~apple~CloudDocs/HealthAutoExport")
APPLE_HEALTH_DIR = Path(os.path.expanduser(_apple_dir))


def have_oura() -> bool:
    return bool(OURA_TOKEN)


def have_eightsleep() -> bool:
    return bool(EIGHTSLEEP_EMAIL and EIGHTSLEEP_PASSWORD)


def have_strava() -> bool:
    return bool(STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET and STRAVA_REFRESH_TOKEN)


def have_apple() -> bool:
    return APPLE_HEALTH_DIR.exists()
