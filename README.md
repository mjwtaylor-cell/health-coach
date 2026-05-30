# Health Coach

A private, local health/fitness/nutrition tracker + planner for Matt.
Pulls Oura, Eight Sleep, and Apple Health into one SQLite DB, and turns recovery +
training load + a personal profile into a daily training call and nutrition targets.

Primary goal: **fat loss**, while preserving muscle and respecting recovery.

## Layout
```
profile.md            # ← personalization spine. Edit when goals/stats change.
config.py             # paths + credentials (from .env)
db.py                 # SQLite schema + upserts
sources/
  oura.py             # official API v2
  eightsleep.py       # unofficial API (secondary, fails soft)
  apple_health.py     # reads Health Auto Export JSON from a watched folder
pipeline.py           # fetch all sources -> DB  (idempotent, safe to re-run)
planner.py            # recovery + load + profile -> today's plan
checkin.py            # evening nutrition check-in + saves tomorrow's plan
dashboard.py          # Streamlit dashboard
```

## Setup
```bash
cd ~/projects/health-coach
cp .env.example .env          # then fill in tokens (see below)
.venv/bin/python pipeline.py  # pull last 30 days
.venv/bin/streamlit run dashboard.py
```

### Credentials (.env)
- **Oura** — create a Personal Access Token at
  https://cloud.ouraring.com/personal-access-tokens → `OURA_TOKEN`
- **Eight Sleep** — your account `EIGHTSLEEP_EMAIL` / `EIGHTSLEEP_PASSWORD` (unofficial API)
- **Apple Health** — install **Health Auto Export** (iOS), set up an automation that
  exports JSON to the folder in `APPLE_HEALTH_DIR` (iCloud Drive). Default:
  `~/Library/Mobile Documents/com~apple~CloudDocs/HealthAutoExport`

## Daily use
- Morning: open the dashboard (or read the saved plan) for today's call + session.
- Evening: `.venv/bin/python checkin.py` — log rough intake; it prints tomorrow's plan.
- `pipeline.py` can be scheduled (cron / launchd) to refresh data automatically.

## Status / TODO
- [ ] Fill personal stats in `profile.md` (age/sex/height/weight) to unlock calorie targets
- [ ] Add credentials and run a real pull to calibrate field mappings
- [ ] Calibrate `apple_health.py` against a real Health Auto Export file
- [ ] Calibrate `eightsleep.py` field mapping against a real response
- [ ] Optional: automate `pipeline.py` on a schedule; add a weekly trends/insights view
