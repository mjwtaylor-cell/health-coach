"""Evening check-in: capture rough nutrition, persist it, and save tomorrow's plan.

Run interactively:   python checkin.py
The planner reads these check-ins to keep the deficit honest over time.
"""
from __future__ import annotations

import datetime as dt
import json

import planner
from config import CHECKINS_DIR
from db import init_db, upsert


def ask(prompt, cast=float, default=None):
    raw = input(prompt).strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        return default


def run() -> None:
    init_db()
    today = dt.date.today().isoformat()
    print(f"\n— Evening check-in for {today} —  (Enter to skip any field)\n")

    cals = ask("Rough calories today? ", float)
    protein = ask("Protein (g)? ", float)
    alcohol = ask("Alcohol units? ", float, 0)
    hunger = ask("Hunger 1–5 (1=stuffed, 5=ravenous)? ", int)
    notes = input("Notes (stress, soreness, anything)? ").strip()

    upsert("checkins", [{
        "date": today, "est_calories": cals, "protein_g": protein,
        "alcohol_units": alcohol, "hunger": hunger, "notes": notes,
    }])
    (CHECKINS_DIR / f"{today}.json").write_text(json.dumps({
        "date": today, "est_calories": cals, "protein_g": protein,
        "alcohol_units": alcohol, "hunger": hunger, "notes": notes,
    }, indent=2))

    # Plan for tomorrow
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    plan = planner.make_plan(tomorrow)
    upsert("plans", [plan])

    print("\n=== Tomorrow's plan ===")
    print(f"  Date:     {plan['date']}")
    print(f"  Call:     {plan['training_call'].upper()}")
    print(f"  Session:  {plan['session']}")
    if plan["calorie_target"]:
        print(f"  Fuel:     {plan['calorie_target']:.0f} kcal / {plan['protein_target']:.0f} g protein")
    print(f"  Why:      {plan['rationale']}\n")


if __name__ == "__main__":
    run()
