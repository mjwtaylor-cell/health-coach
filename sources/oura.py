"""Oura Ring — official API v2. https://cloud.ouraring.com/v2/docs

Personal Access Token auth. Pulls daily sleep, readiness, activity, and
workouts, mapped into the project's DB schema.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import OURA_TOKEN  # noqa: E402

BASE = "https://api.ouraring.com/v2/usercollection"


def _get(endpoint: str, start: str, end: str) -> list[dict]:
    resp = requests.get(
        f"{BASE}/{endpoint}",
        headers={"Authorization": f"Bearer {OURA_TOKEN}"},
        params={"start_date": start, "end_date": end},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def _mins(seconds) -> float | None:
    return round(seconds / 60, 1) if seconds is not None else None


def fetch(days_back: int = 30) -> dict[str, list[dict]]:
    end = dt.date.today()
    start = end - dt.timedelta(days=days_back)
    s, e = start.isoformat(), end.isoformat()

    out: dict[str, list[dict]] = {"sleep": [], "readiness": [], "activity_daily": [], "workouts": []}

    # Detailed sleep periods → take the 'long_sleep' / main period per day
    for r in _get("sleep", s, e):
        if r.get("type") not in (None, "long_sleep", "sleep"):
            continue
        out["sleep"].append({
            "date": r.get("day"), "source": "oura",
            "total_min": _mins(r.get("total_sleep_duration")),
            "deep_min": _mins(r.get("deep_sleep_duration")),
            "rem_min": _mins(r.get("rem_sleep_duration")),
            "light_min": _mins(r.get("light_sleep_duration")),
            "awake_min": _mins(r.get("awake_time")),
            "efficiency": r.get("efficiency"),
            "latency_min": _mins(r.get("latency")),
            "hr_avg": r.get("average_heart_rate"),
            "hr_low": r.get("lowest_heart_rate"),
            "hrv_avg": r.get("average_hrv"),
            "temp_dev": (r.get("readiness") or {}).get("temperature_deviation"),
            "spo2": None,
        })

    for r in _get("daily_readiness", s, e):
        # NOTE: contributors.* are 0-100 SUB-SCORES, not bpm/ms. True resting HR and
        # HRV live in the sleep table (hr_low / hrv_avg). Keep these as score signals only.
        contrib = r.get("contributors") or {}
        out["readiness"].append({
            "date": r.get("day"), "source": "oura",
            "score": r.get("score"),
            "hrv_balance": contrib.get("hrv_balance"),
            "rhr": contrib.get("resting_heart_rate"),
            "temp_dev": r.get("temperature_deviation"),
            "recovery_index": contrib.get("recovery_index"),
        })

    for r in _get("daily_activity", s, e):
        out["activity_daily"].append({
            "date": r.get("day"), "source": "oura",
            "steps": r.get("steps"),
            "active_kcal": r.get("active_calories"),
            "total_kcal": r.get("total_calories"),
            "exercise_min": None,
            "stand_hours": None,
            "score": r.get("score"),
        })

    for r in _get("workout", s, e):
        out["workouts"].append({
            "workout_id": f"oura-{r.get('id')}",
            "date": r.get("day"), "source": "oura",
            "type": r.get("activity"),
            "start_ts": r.get("start_datetime"),
            "duration_min": None,
            "active_kcal": r.get("calories"),
            "distance_km": round(r["distance"] / 1000, 2) if r.get("distance") else None,
            "hr_avg": None, "hr_max": None,
        })

    return out


if __name__ == "__main__":
    import json
    data = fetch(7)
    print(json.dumps({k: len(v) for k, v in data.items()}, indent=2))
