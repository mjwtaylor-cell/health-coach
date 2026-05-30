"""The planner: combine recovery + recent training load + profile -> today's plan.

Deterministic and transparent (every call comes with a rationale). The richer,
natural-language coaching layer happens in the evening check-in; this is the
engine that decides intensity, the session, and the nutrition targets.
"""
from __future__ import annotations

import datetime as dt
import re

from config import PROFILE_PATH
from db import query

OFFICE_DAYS = {1, 2, 3}  # Tue, Wed, Thu  (Mon=0 .. Sun=6)


# ---------- profile parsing ----------
def parse_profile() -> dict:
    """Pull the few numeric fields the math needs from profile.md."""
    text = PROFILE_PATH.read_text() if PROFILE_PATH.exists() else ""
    p: dict = {"raw": text}

    def grab(label):
        m = re.search(rf"\*\*{label}.*?:\*\*\s*(.+)", text)
        return m.group(1).strip() if m else None

    def num(s):
        if not s:
            return None
        m = re.search(r"[\d.]+", s)
        return float(m.group()) if m else None

    p["age"] = num(grab("Age"))
    sex = (grab("Sex") or "").lower()
    p["sex"] = "male" if sex.startswith("m") else "female" if sex.startswith("f") else None

    h = grab("Height")
    if h:
        cm = re.search(r"([\d.]+)\s*cm", h.lower())  # prefer an explicit cm value
        ft = re.search(r"(\d+)\s*[\'ft]", h)
        inch = re.search(r"(\d+)\s*[\"in]", h)
        if cm:
            p["height_cm"] = float(cm.group(1))
        elif ft:  # ft/in like 5'10"
            p["height_cm"] = round(int(ft.group(1)) * 30.48 + (int(inch.group(1)) if inch else 0) * 2.54, 1)

    w = grab("Current weight")
    wv = num(w)
    if wv is not None:
        p["weight_kg"] = round(wv * 0.4536, 1) if "lb" in w.lower() else wv

    return p


# ---------- data access ----------
def _latest(table: str, prefer_source="oura") -> dict | None:
    rows = query(
        f"SELECT * FROM {table} ORDER BY (source=?) DESC, date DESC LIMIT 1",
        (prefer_source,),
    )
    return rows[0] if rows else None


def _runs_this_week() -> int:
    monday = (dt.date.today() - dt.timedelta(days=dt.date.today().weekday())).isoformat()
    # distinct run days, so Oura+Strava on the same day count once
    return len(query(
        "SELECT DISTINCT date FROM workouts WHERE date >= ? AND lower(type) LIKE '%run%'",
        (monday,),
    ))


def _hard_yesterday() -> bool:
    y = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    rows = query("SELECT training_call FROM plans WHERE date=?", (y,))
    return bool(rows and rows[0]["training_call"] == "hard")


# ---------- decisioning ----------
def hr_zones() -> dict:
    """Karvonen (heart-rate-reserve) zones from age (Tanaka max HR) + measured RHR."""
    age = parse_profile().get("age")
    if not age:
        return {}
    max_hr = round(208 - 0.7 * age)
    s = _latest("sleep")
    rhr = (s.get("hr_low") if s else None) or 50
    hrr = max_hr - rhr

    def z(lo, hi):
        return (round(rhr + lo * hrr), round(rhr + hi * hrr))

    return {"max_hr": max_hr, "rhr": round(rhr),
            "zone2": z(0.60, 0.70), "zone3": z(0.70, 0.80), "zone4": z(0.80, 0.90)}


def training_call(readiness_score: float | None) -> str:
    if readiness_score is None:
        return "moderate"  # no signal — default cautious-moderate
    if readiness_score >= 85:
        return "hard"
    if readiness_score >= 70:
        return "moderate"
    if readiness_score >= 55:
        return "easy"
    return "rest"


def choose_session(call: str, today: dt.date, runs_done: int, zones: dict) -> str:
    office = today.weekday() in OFFICE_DAYS
    need_runs = runs_done < 3
    z2 = f" (keep HR ≤ {zones['zone2'][1]} bpm)" if zones else ""
    z4 = f" (push to {zones['zone4'][0]}–{zones['zone4'][1]} bpm on the hard reps)" if zones else ""

    if call == "rest":
        return "Rest / light walk + mobility. Recovery is the priority today."
    if call == "easy":
        if need_runs:
            return f"Easy Zone-2 run, 30–40 min{z2}. This is the fat-burning sweet spot — stay under the ceiling even if it feels too easy."
        return "Light Apple Fitness+ session or 20–30 min easy spin / walk."

    if office:
        # office day: equipment-light → run-focused
        if call == "hard" and need_runs:
            return f"Run intervals: 10 min easy, then 6×(2 min hard{z4} / 90 s easy), 10 min cool-down."
        if need_runs:
            return f"Moderate Zone-2 run, 35–45 min{z2}."
        return "Bodyweight circuit (Apple Fitness+ HIIT or 20 min EMOM) — equipment-light for the office day."

    # home day: best window for weights
    if call == "hard":
        return ("Home strength, ≤40 min, full-body: squat/hinge/push/pull supersets, "
                "3 rounds, progressive load. Finish with 10 min easy cardio.")
    return (f"Home strength, ≤40 min, full-body at moderate effort — or a 45–60 min "
            f"Zone-2 run{z2} if you'd rather log a run today.")


def nutrition_targets(profile: dict, call: str) -> dict:
    kg, cm, age, sex = profile.get("weight_kg"), profile.get("height_cm"), profile.get("age"), profile.get("sex")
    if not all([kg, cm, age, sex]):
        return {"calorie_target": None, "protein_target": None,
                "note": "Fill Age / Sex / Height / Current weight in profile.md to enable calorie & protein targets."}
    bmr = 10 * kg + 6.25 * cm - 5 * age + (5 if sex == "male" else -161)
    maintenance = bmr * 1.45  # lightly active baseline
    deficit = 500 if call in ("hard", "moderate") else 350  # smaller cut on easy/rest days
    calorie_target = round((maintenance - deficit) / 10) * 10
    protein_target = round(kg * 2.0)  # high protein to preserve muscle in a deficit
    return {"calorie_target": calorie_target, "protein_target": protein_target,
            "note": f"~{deficit} kcal deficit vs est. maintenance {round(maintenance)} kcal."}


def make_plan(for_date: dt.date | None = None) -> dict:
    today = for_date or dt.date.today()
    profile = parse_profile()
    readiness = _latest("readiness")
    sleep = _latest("sleep")
    score = readiness.get("score") if readiness else None

    call = training_call(score)
    if call == "hard" and _hard_yesterday():
        call = "moderate"  # avoid back-to-back hard days

    runs_done = _runs_this_week()
    zones = hr_zones()
    session = choose_session(call, today, runs_done, zones)
    nut = nutrition_targets(profile, call)

    bits = []
    if score is not None:
        bits.append(f"Oura readiness {round(score)}")
    if sleep and sleep.get("total_min"):
        bits.append(f"slept {round(sleep['total_min']/60,1)} h")
    bits.append(f"{runs_done}/3 runs this week")
    if today.weekday() in OFFICE_DAYS:
        bits.append("office day (equipment-light)")
    rationale = "; ".join(bits) + f" → call: {call}."

    return {
        "date": today.isoformat(),
        "training_call": call,
        "session": session,
        "calorie_target": nut["calorie_target"],
        "protein_target": nut["protein_target"],
        "rationale": rationale + " " + nut["note"],
        "created_ts": "",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(make_plan(), indent=2))
