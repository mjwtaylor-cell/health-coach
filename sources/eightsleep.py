"""Eight Sleep — UNOFFICIAL API. No public/supported API exists.

This uses the same auth flow the mobile app uses (public client credentials).
It can break if Eight Sleep changes their backend. The pipeline treats this as a
secondary signal (Oura is the primary recovery source), so failures here are
caught and logged, never fatal.

Calibrate field mapping against a real response the first time creds are added.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import EIGHTSLEEP_EMAIL, EIGHTSLEEP_PASSWORD  # noqa: E402

# Public client credentials extracted from the Eight Sleep mobile app.
CLIENT_ID = "0894c7f33bb94800a03f1f4df13a4f38"
CLIENT_SECRET = "f0954a3ed5763ba3d06834c73731a32f15f168f47d4f164751275def86db0c76"
AUTH_URL = "https://auth-api.8slp.net/v1/tokens"
CLIENT_API = "https://client-api.8slp.net/v1"


def _auth() -> tuple[str, str]:
    resp = requests.post(AUTH_URL, json={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "grant_type": "password",
        "username": EIGHTSLEEP_EMAIL, "password": EIGHTSLEEP_PASSWORD,
    }, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    return body["access_token"], body["userId"]


def fetch(days_back: int = 30) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {"sleep": []}
    if not (EIGHTSLEEP_EMAIL and EIGHTSLEEP_PASSWORD):
        return out
    try:
        token, user_id = _auth()
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(
            f"{CLIENT_API}/users/{user_id}/intervals",
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        for iv in resp.json().get("intervals", []):
            ts = iv.get("ts", "")
            day = ts[:10]
            if not day:
                continue
            stages = iv.get("stages", [])
            def stage_min(name):
                secs = sum(s.get("duration", 0) for s in stages if s.get("stage") == name)
                return round(secs / 60, 1) if secs else None
            out["sleep"].append({
                "date": day, "source": "eightsleep",
                "total_min": round(sum(s.get("duration", 0) for s in stages) / 60, 1) if stages else None,
                "deep_min": stage_min("deep"),
                "rem_min": stage_min("rem"),
                "light_min": stage_min("light"),
                "awake_min": stage_min("awake") or stage_min("out"),
                "efficiency": None, "latency_min": None,
                "hr_avg": (iv.get("timeseries", {}).get("heartRate") or [[None, None]])[0][1] if iv.get("timeseries") else None,
                "hr_low": None,
                "hrv_avg": None, "temp_dev": None, "spo2": None,
            })
    except Exception as exc:  # unofficial API — never fatal
        print(f"[eightsleep] skipped ({type(exc).__name__}: {exc})")
    return out


if __name__ == "__main__":
    print({k: len(v) for k, v in fetch(7).items()})
