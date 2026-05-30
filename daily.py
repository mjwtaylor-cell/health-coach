"""Daily job (run by launchd each morning): refresh all sources + save today's plan.

Pulls fresh data, computes today's training call + nutrition targets, and persists
the plan so the dashboard and any morning brief reflect the latest recovery.
"""
from __future__ import annotations

import datetime as dt

import pipeline
import planner
from db import init_db, upsert


def run() -> None:
    init_db()
    pipeline.run(days_back=14)            # rolling refresh; full history already stored
    plan = planner.make_plan(dt.date.today())
    upsert("plans", [plan])
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    cals = f"{plan['calorie_target']:.0f} kcal" if plan["calorie_target"] else "targets off"
    print(f"[{stamp}] {plan['training_call'].upper()} | {cals}")
    print(f"  {plan['session']}")
    print(f"  {plan['rationale']}")


if __name__ == "__main__":
    run()
