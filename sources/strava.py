"""Strava — official API v3. https://developers.strava.com

Uses the stored refresh token to mint a short-lived access token, then pulls
recent activities (runs, rides, walks, weight training, etc.) into the workouts
table. Strava typically aggregates Apple Watch + Nike Run Club runs, so this is
the primary source of truth for workouts.
"""
from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN  # noqa: E402

BASE = "https://www.strava.com/api/v3"


def _access_token() -> str:
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": STRAVA_CLIENT_ID, "client_secret": STRAVA_CLIENT_SECRET,
        "grant_type": "refresh_token", "refresh_token": STRAVA_REFRESH_TOKEN,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch(days_back: int = 30) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {"workouts": []}
    if not (STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET and STRAVA_REFRESH_TOKEN):
        return out

    token = _access_token()
    after = int(time.mktime((dt.date.today() - dt.timedelta(days=days_back)).timetuple()))
    page = 1
    while True:
        resp = requests.get(
            f"{BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {token}"},
            params={"after": after, "per_page": 100, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for a in batch:
            start = a.get("start_date_local", "")
            out["workouts"].append({
                "workout_id": f"strava-{a.get('id')}",
                "date": start[:10],
                "source": "strava",
                "type": a.get("type"),                       # Run, Ride, Walk, WeightTraining, ...
                "start_ts": start,
                "duration_min": round(a.get("moving_time", 0) / 60, 1) if a.get("moving_time") else None,
                "active_kcal": a.get("calories") or (round(a["kilojoules"] / 4.184) if a.get("kilojoules") else None),
                "distance_km": round(a["distance"] / 1000, 2) if a.get("distance") else None,
                "hr_avg": a.get("average_heartrate"),
                "hr_max": a.get("max_heartrate"),
            })
        if len(batch) < 100:
            break
        page += 1

    return out


if __name__ == "__main__":
    data = fetch(30)
    print(f"{len(data['workouts'])} activities")
    for w in data["workouts"][:5]:
        print(f"  {w['date']} {w['type']:14} {w['distance_km']}km {w['duration_min']}min HR{w['hr_avg']}")
