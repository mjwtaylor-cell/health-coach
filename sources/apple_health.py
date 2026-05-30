"""Apple Health — reads JSON dropped by the Health Auto Export iOS app.

Health Auto Export writes files containing {"data": {"metrics": [...], "workouts": [...]}}.
Metric names vary slightly by app version; the MAP below covers the common ones and
is easy to extend once we see a real export. Unknown metrics are ignored.

Each metric entry looks like:
  {"name": "step_count", "units": "count", "data": [{"date": "2024-01-01 00:00:00 +0000", "qty": 1234}, ...]}
We roll daily-granularity metrics up by calendar date.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import APPLE_HEALTH_DIR  # noqa: E402

# metric name -> (table, column)
MAP = {
    "step_count": ("activity_daily", "steps"),
    "active_energy": ("activity_daily", "active_kcal"),
    "apple_exercise_time": ("activity_daily", "exercise_min"),
    "apple_stand_hour": ("activity_daily", "stand_hours"),
    "resting_heart_rate": ("readiness", "rhr"),
    "heart_rate_variability": ("readiness", "hrv_balance"),
    "body_mass": ("body", "weight_kg"),
    "body_fat_percentage": ("body", "body_fat_pct"),
    "vo2_max": ("body", "vo2max"),
}


def _date(s: str) -> str:
    # "2024-01-01 00:00:00 +0000" -> "2024-01-01"
    return s[:10]


def fetch() -> dict[str, list[dict]]:
    out = {"activity_daily": [], "readiness": [], "body": [], "workouts": []}
    if not APPLE_HEALTH_DIR.exists():
        return out

    # tables keyed by date, accumulate columns
    rows: dict[str, dict[str, dict]] = {t: defaultdict(dict) for t in ("activity_daily", "readiness", "body")}
    seen_workouts: set[str] = set()

    for fp in sorted(APPLE_HEALTH_DIR.glob("*.json")):
        try:
            payload = json.loads(fp.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        data = payload.get("data", payload)

        for metric in data.get("metrics", []):
            name = metric.get("name")
            if name not in MAP:
                continue
            table, col = MAP[name]
            for point in metric.get("data", []):
                d = _date(point.get("date", ""))
                if not d:
                    continue
                qty = point.get("qty")
                # body_fat comes as fraction; normalize to %
                if name == "body_fat_percentage" and qty is not None and qty < 1:
                    qty *= 100
                rows[table][d][col] = qty

        for w in data.get("workouts", []):
            wid = "apple-" + (w.get("id") or f"{w.get('start')}-{w.get('name')}")
            if wid in seen_workouts:
                continue
            seen_workouts.add(wid)
            start = w.get("start", "")
            dur = w.get("duration")  # seconds (sometimes minutes — calibrate on real data)
            dur_min = round(dur / 60, 1) if dur and dur > 600 else dur
            out["workouts"].append({
                "workout_id": wid,
                "date": _date(start),
                "source": "apple",
                "type": w.get("name"),
                "start_ts": start,
                "duration_min": dur_min,
                "active_kcal": (w.get("activeEnergyBurned") or {}).get("qty") if isinstance(w.get("activeEnergyBurned"), dict) else w.get("activeEnergyBurned"),
                "distance_km": (w.get("distance") or {}).get("qty") if isinstance(w.get("distance"), dict) else w.get("distance"),
                "hr_avg": (w.get("avgHeartRate") or {}).get("qty") if isinstance(w.get("avgHeartRate"), dict) else w.get("avgHeartRate"),
                "hr_max": (w.get("maxHeartRate") or {}).get("qty") if isinstance(w.get("maxHeartRate"), dict) else w.get("maxHeartRate"),
            })

    for table, by_date in rows.items():
        for d, cols in by_date.items():
            out[table].append({"date": d, "source": "apple", **cols})

    return out


if __name__ == "__main__":
    data = fetch()
    print({k: len(v) for k, v in data.items()})
