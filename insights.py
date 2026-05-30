"""Weekly insights: mine the history for patterns that matter to the fat-loss goal.

Each insight is a dict: {title, headline, detail, tone}. tone ∈ {good, warn, info}.
Everything degrades gracefully when there isn't enough data yet.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

import planner
from db import query_df as _df


def _corr(a: pd.Series, b: pd.Series) -> float | None:
    m = pd.concat([a, b], axis=1).dropna()
    if len(m) < 6:
        return None
    c = m.iloc[:, 0].corr(m.iloc[:, 1])
    return None if pd.isna(c) else round(c, 2)


def compute() -> list[dict]:
    out: list[dict] = []
    sleep = _df("SELECT date, total_min, hrv_avg, hr_low FROM sleep WHERE source='oura' ORDER BY date")
    readiness = _df("SELECT date, score FROM readiness WHERE source='oura' ORDER BY date")
    runs = _df("SELECT date, hr_avg, distance_km, duration_min FROM workouts WHERE lower(type) LIKE '%run%' AND hr_avg IS NOT NULL ORDER BY date")
    checkins = _df("SELECT date, alcohol_units FROM checkins")
    zones = planner.hr_zones()

    # 1) Run intensity distribution vs zones — the headline fat-loss finding
    if not runs.empty and zones:
        z2_hi = zones["zone2"][1]
        easy = (runs["hr_avg"] <= z2_hi).sum()
        total = len(runs)
        pct_easy = round(100 * easy / total)
        tone = "good" if pct_easy >= 50 else "warn"
        out.append({
            "title": "Run intensity",
            "headline": f"{pct_easy}% of your runs are in Zone 2 (≤{z2_hi} bpm)",
            "detail": (f"{easy}/{total} runs were easy/fat-burning. For fat loss, aim for ~70–80% of runs "
                       f"in Zone 2. Avg run HR is {round(runs['hr_avg'].mean())} bpm."
                       + ("" if pct_easy >= 50 else " You're running too hard, too often — slow most runs down.")),
            "tone": tone,
        })

    # 2) Sleep → next-day readiness
    m = pd.merge(sleep[["date", "total_min"]], readiness, on="date", how="inner")
    c = _corr(m["total_min"], m["score"]) if not m.empty else None
    if c is not None:
        out.append({
            "title": "Sleep → readiness",
            "headline": f"Sleep duration vs readiness: r = {c}",
            "detail": ("Strong link — protecting sleep duration directly lifts your readiness." if c >= 0.4
                       else "Weaker than expected — your readiness is driven more by other factors (HRV, temp, prior load)."),
            "tone": "good" if c >= 0.4 else "info",
        })

    # 3) Hard run → next-day readiness cost
    if not runs.empty and not readiness.empty and zones:
        rd = readiness.set_index("date")["score"].to_dict()
        deltas = []
        for _, r in runs.iterrows():
            nxt = (dt.date.fromisoformat(r["date"]) + dt.timedelta(days=1)).isoformat()
            if r["hr_avg"] >= zones["zone3"][0] and nxt in rd and r["date"] in rd:
                deltas.append(rd[nxt] - rd[r["date"]])
        if len(deltas) >= 4:
            avg = round(sum(deltas) / len(deltas), 1)
            out.append({
                "title": "Hard runs → recovery",
                "headline": f"Readiness changes {avg:+} pts the day after a Zone 3+ run",
                "detail": (f"Across {len(deltas)} hard runs. "
                           + ("That's a real recovery cost — keep hard efforts to 1×/week." if avg <= -2
                              else "Your recovery handles them well, but easy runs still burn more fat per session.")),
                "tone": "warn" if avg <= -2 else "info",
            })

    # 4) HRV trend (last 7d vs prior 7d)
    s = sleep.dropna(subset=["hrv_avg"])
    if len(s) >= 14:
        recent = s["hrv_avg"].tail(7).mean()
        prior = s["hrv_avg"].tail(14).head(7).mean()
        diff = round(recent - prior, 1)
        out.append({
            "title": "HRV trend",
            "headline": f"7-day HRV {('up' if diff >= 0 else 'down')} {abs(diff)} ms ({round(recent)} vs {round(prior)} ms)",
            "detail": ("Trending up — recovery and adaptation are improving." if diff >= 0
                       else "Trending down — watch cumulative load, sleep, and stress."),
            "tone": "good" if diff >= 0 else "warn",
        })

    # 5) Alcohol → HRV (needs check-in data)
    if not checkins.empty and checkins["alcohol_units"].notna().any():
        a = pd.merge(checkins, sleep[["date", "hrv_avg"]], on="date", how="inner").dropna()
        if len(a) >= 6:
            drink = a[a["alcohol_units"] > 0]["hrv_avg"].mean()
            sober = a[a["alcohol_units"] == 0]["hrv_avg"].mean()
            if pd.notna(drink) and pd.notna(sober):
                out.append({
                    "title": "Alcohol → HRV",
                    "headline": f"HRV {round(sober - drink)} ms lower on drinking nights ({round(drink)} vs {round(sober)} ms)",
                    "detail": "Alcohol is measurably suppressing your overnight recovery.",
                    "tone": "warn",
                })
    else:
        out.append({
            "title": "Alcohol → HRV",
            "headline": "Not enough check-in data yet",
            "detail": "Log evening check-ins (alcohol units) for ~2 weeks and this correlation unlocks.",
            "tone": "info",
        })

    # 6) Weekly run volume
    if not runs.empty:
        runs["week"] = pd.to_datetime(runs["date"]).dt.to_period("W").astype(str)
        wk = runs.groupby("week")["distance_km"].sum().round(1)
        if len(wk) >= 2:
            out.append({
                "title": "Run volume",
                "headline": f"Last full week: {wk.iloc[-2]} km (avg {round(wk.mean(),1)} km/wk)",
                "detail": "Build easy (Zone 2) volume gradually — no more than ~10%/week — to raise your aerobic base without spiking injury risk.",
                "tone": "info",
            })

    return out


if __name__ == "__main__":
    for i in compute():
        print(f"[{i['tone'].upper()}] {i['title']}: {i['headline']}")
        print(f"    {i['detail']}\n")
