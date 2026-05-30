"""Personalized AI coaching via Claude.

Assembles Matt's context (profile + recent recovery, training, insights, plan,
check-ins) and asks Claude for 3-5 specific, data-grounded coaching thoughts.

- Reads ANTHROPIC_API_KEY from config.secret (env or st.secrets); no key → no-op.
- Results are persisted per-day in the DB (coach_tips table), so the model is
  called at most once per day even across app restarts.
- Model defaults to claude-opus-4-8; override with HC_COACH_MODEL secret
  (e.g. claude-sonnet-4-6 to halve cost).
"""
from __future__ import annotations

import datetime as dt
import json
import statistics as stats

import config
import insights
import planner
from db import query, upsert

MODEL = config.secret("HC_COACH_MODEL") or "claude-opus-4-8"

COACH_SYSTEM = """You are Matt's personal health & performance coach. You speak directly to Matt (second person), like a sharp, supportive coach who actually knows his data.

Your job: read his recent data and profile, then give 3-5 specific, actionable coaching thoughts for the next day or two.

Rules:
- Be SPECIFIC and reference his actual numbers (readiness, HRV, run HR, weight, etc.). No generic advice.
- His #1 goal is FAT LOSS while preserving muscle. Weigh tips toward that.
- Tie every tip to something concrete in his data or profile — if you can't ground it, don't say it.
- Be concise: a punchy title + 1-3 sentences. Specifics over adjectives.
- Cover a mix when the data supports it: recovery, training (incl. his Zone-2 habit), nutrition, sleep, and notable trends.
- Encouraging but honest. If something needs to change, say so plainly with the number behind it.
- Do NOT restate the auto-generated plan verbatim — add insight beyond it.

His full profile follows; treat it as ground truth about who he is and what he's optimizing for."""

TIPS_SCHEMA = {
    "type": "object",
    "properties": {
        "tips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "tip": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["recovery", "training", "nutrition", "sleep", "trend", "mindset"],
                    },
                },
                "required": ["title", "tip", "category"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["tips"],
    "additionalProperties": False,
}


def available() -> bool:
    return bool(config.secret("ANTHROPIC_API_KEY"))


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(stats.mean(vals), 1) if vals else None


def _digest() -> str:
    """Compact markdown snapshot of Matt's recent data for the model."""
    p = []
    plan = planner.make_plan()
    z = planner.hr_zones()
    p.append(f"## Today ({dt.date.today():%A %b %-d})\n"
             f"Auto-plan call: {plan['training_call']}. Session: {plan['session']}\n"
             f"Fuel targets: {plan['calorie_target']} kcal / {plan['protein_target']} g protein\n"
             f"Rationale: {plan['rationale']}")
    if z:
        p.append(f"## HR zones\nZone 2 {z['zone2'][0]}–{z['zone2'][1]}, Zone 3 {z['zone3'][0]}–{z['zone3'][1]}, "
                 f"Zone 4 {z['zone4'][0]}–{z['zone4'][1]} bpm (maxHR {z['max_hr']}, RHR {z['rhr']})")

    rec = query("SELECT score FROM readiness WHERE source='oura' ORDER BY date DESC LIMIT 14")
    slp = query("SELECT total_min, hrv_avg, hr_low FROM sleep WHERE source='oura' ORDER BY date DESC LIMIT 14")
    if rec:
        scores = [r["score"] for r in rec]
        p.append(f"## Recovery (last {len(rec)} d)\n"
                 f"Readiness avg {_avg(scores)} (latest {scores[0]}, range {min(scores)}–{max(scores)})\n"
                 f"HRV avg {_avg([s['hrv_avg'] for s in slp])} ms, RHR avg {_avg([s['hr_low'] for s in slp])} bpm, "
                 f"sleep avg {_avg([(s['total_min'] or 0)/60 for s in slp])} h")

    wk = query("SELECT date, type, distance_km, duration_min, hr_avg FROM workouts ORDER BY date DESC LIMIT 12")
    if wk:
        lines = [f"- {w['date']} {w['type']} {w['distance_km'] or '-'}km {w['duration_min'] or '-'}min "
                 f"avgHR {round(w['hr_avg']) if w['hr_avg'] else '-'}" for w in wk]
        p.append("## Recent workouts\n" + "\n".join(lines))

    ci = query("SELECT date, est_calories, protein_g, alcohol_units, hunger, notes FROM checkins ORDER BY date DESC LIMIT 7")
    if ci:
        lines = [f"- {c['date']}: {c['est_calories'] or '?'} kcal, {c['protein_g'] or '?'}g protein, "
                 f"{c['alcohol_units'] or 0} alcohol, hunger {c['hunger'] or '?'}"
                 + (f", note: {c['notes']}" if c.get('notes') else "") for c in ci]
        p.append("## Recent nutrition check-ins\n" + "\n".join(lines))
    else:
        p.append("## Nutrition check-ins\nNone logged yet.")

    cards = insights.compute()
    if cards:
        p.append("## Rule-based insights\n" + "\n".join(f"- [{c['tone']}] {c['headline']}: {c['detail']}" for c in cards))

    return "\n\n".join(p)


def generate() -> list[dict] | None:
    """Call Claude for fresh tips. Returns None if no API key or on failure."""
    if not available():
        return None
    try:
        import anthropic
    except ImportError:
        return None

    profile = config.PROFILE_PATH.read_text() if config.PROFILE_PATH.exists() else ""
    client = anthropic.Anthropic(api_key=config.secret("ANTHROPIC_API_KEY"))
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2500,
            thinking={"type": "adaptive"},
            # Static prefix (instructions + profile) cached; volatile data goes in the user turn.
            system=[{
                "type": "text",
                "text": f"{COACH_SYSTEM}\n\n# MATT'S PROFILE\n{profile}",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": f"Here's my latest data. Give me 3-5 specific coaching thoughts.\n\n{_digest()}",
            }],
            output_config={"format": {"type": "json_schema", "schema": TIPS_SCHEMA}},
        )
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text).get("tips", [])
    except Exception as exc:
        print(f"[coach] generation failed: {type(exc).__name__}: {exc}")
        return None


def get_today() -> list[dict] | None:
    """Return today's tips, generating + persisting them once per day."""
    today = dt.date.today().isoformat()
    rows = query("SELECT tips_json FROM coach_tips WHERE date=?", (today,))
    if rows:
        try:
            return json.loads(rows[0]["tips_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    tips = generate()
    if tips:
        upsert("coach_tips", [{"date": today, "tips_json": json.dumps(tips), "created_ts": ""}])
    return tips


if __name__ == "__main__":
    print(f"model={MODEL} available={available()}")
    for t in (get_today() or []):
        print(f"[{t['category']}] {t['title']}: {t['tip']}")
