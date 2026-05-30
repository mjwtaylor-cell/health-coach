"""Health Coach dashboard.  Local: .venv/bin/streamlit run dashboard.py

When deployed, set the APP_PASSWORD env var to require a login. Left unset
locally, the login gate is skipped.
"""
from __future__ import annotations

import datetime as dt
import os

import pandas as pd
import plotly.express as px
import streamlit as st

import insights
import planner
from config import DB_PATH
from db import init_db, query_df, upsert

st.set_page_config(page_title="Health Coach", page_icon="🏃", layout="wide",
                   initial_sidebar_state="expanded")
init_db()


def _gate() -> None:
    """Simple single-user password gate. Active only when APP_PASSWORD is set."""
    pw = os.getenv("APP_PASSWORD")
    if not pw:
        return
    if st.session_state.get("authed"):
        return
    st.title("🏃 Health Coach")
    entered = st.text_input("Password", type="password")
    if entered and entered == pw:
        st.session_state["authed"] = True
        st.rerun()
    elif entered:
        st.error("Incorrect password.")
    st.stop()


_gate()

# Cloud: pull fresh data when the app is opened and the cache is stale (>3h).
# Single-user app → opening it on your phone IS the trigger; no separate scheduler needed.
if os.getenv("AUTO_REFRESH") == "1":
    @st.cache_data(ttl=3 * 3600, show_spinner="Refreshing your latest data…")
    def _auto_pull() -> bool:
        import pipeline
        pipeline.run(days_back=14)
        return True

    _auto_pull()


def q(sql: str) -> pd.DataFrame:
    return query_df(sql)


# ---------------- Evening check-in (sidebar; works from phone) ----------------
with st.sidebar:
    st.header("🌙 Evening check-in")
    today_iso = dt.date.today().isoformat()
    existing = q(f"SELECT * FROM checkins WHERE date='{today_iso}'")
    if not existing.empty:
        st.success("Logged for today ✓ (resubmit to update)")
    with st.form("checkin"):
        cals = st.number_input("Calories", min_value=0, max_value=8000, step=50, value=None, placeholder="rough estimate")
        protein = st.number_input("Protein (g)", min_value=0, max_value=400, step=5, value=None, placeholder="grams")
        alcohol = st.number_input("Alcohol (units)", min_value=0.0, max_value=20.0, step=1.0, value=0.0)
        hunger = st.slider("Hunger (1=stuffed, 5=ravenous)", 1, 5, 3)
        notes = st.text_input("Notes", placeholder="stress, soreness, anything")
        if st.form_submit_button("Save & plan tomorrow", use_container_width=True):
            upsert("checkins", [{"date": today_iso, "est_calories": cals, "protein_g": protein,
                                 "alcohol_units": alcohol, "hunger": hunger, "notes": notes}])
            tomorrow = dt.date.today() + dt.timedelta(days=1)
            tplan = planner.make_plan(tomorrow)
            upsert("plans", [tplan])
            st.success("Saved. Tomorrow:")
            st.write(f"**{tplan['training_call'].upper()}** — {tplan['session']}")
            if tplan["calorie_target"]:
                st.caption(f"Fuel: {tplan['calorie_target']:.0f} kcal / {tplan['protein_target']:.0f} g protein")


# ---------------- Today's plan ----------------
st.title("🏃 Health Coach")
plan = planner.make_plan()
call_color = {"hard": "🔴", "moderate": "🟠", "easy": "🟢", "rest": "🔵"}.get(plan["training_call"], "⚪")

c1, c2 = st.columns([1, 2])
with c1:
    st.subheader("Today")
    st.metric("Training call", f"{call_color} {plan['training_call'].upper()}")
    if plan["calorie_target"]:
        st.metric("Fuel target", f"{plan['calorie_target']:.0f} kcal")
        st.metric("Protein", f"{plan['protein_target']:.0f} g")
with c2:
    st.subheader("Session")
    st.info(plan["session"])
    st.caption(plan["rationale"])

st.divider()

# ---------------- Recovery ----------------
st.subheader("Recovery")
rec = q("SELECT date, score FROM readiness WHERE source='oura' ORDER BY date")
# True RHR (lowest nightly HR) and HRV come from the sleep record, not readiness sub-scores.
slp = q("SELECT date, total_min, hrv_avg, hr_low FROM sleep WHERE source='oura' ORDER BY date")

if not rec.empty:
    r1 = st.columns(2)
    r1[0].plotly_chart(px.line(rec, x="date", y="score", title="Oura readiness", markers=True, range_y=[0, 100]), use_container_width=True)
    if not slp.empty:
        slp["hours"] = slp["total_min"] / 60
        r1[1].plotly_chart(px.bar(slp, x="date", y="hours", title="Sleep (h)"), use_container_width=True)
        r2 = st.columns(2)
        r2[0].plotly_chart(px.line(slp, x="date", y="hrv_avg", title="HRV (ms)", markers=True), use_container_width=True)
        r2[1].plotly_chart(px.line(slp, x="date", y="hr_low", title="Resting HR (bpm)", markers=True), use_container_width=True)
else:
    st.warning("No recovery data yet. Add your Oura token to `.env` and run `python pipeline.py`.")

st.divider()

# ---------------- Training load ----------------
st.subheader("Training load")
wk = q("SELECT date, type, source, duration_min, distance_km, active_kcal FROM workouts ORDER BY date DESC LIMIT 30")
if not wk.empty:
    runs = (dt.date.today() - dt.timedelta(days=dt.date.today().weekday())).isoformat()
    n_runs = wk[(wk["date"] >= runs) & (wk["type"].str.contains("run", case=False, na=False))].shape[0]
    st.metric("Runs this week", f"{n_runs} / 3")
    st.dataframe(wk, use_container_width=True, hide_index=True)
else:
    st.caption("No workouts logged yet.")

st.divider()

# ---------------- Body & nutrition ----------------
left, right = st.columns(2)
with left:
    st.subheader("Body weight")
    body = q("SELECT date, weight_kg FROM body WHERE weight_kg IS NOT NULL ORDER BY date")
    if not body.empty:
        body["trend"] = body["weight_kg"].rolling(7, min_periods=1).mean()
        st.plotly_chart(px.line(body, x="date", y=["weight_kg", "trend"], title="Weight + 7d trend"), use_container_width=True)
    else:
        st.caption("No weight data yet (smart scale via Apple Health, or log manually).")
with right:
    st.subheader("Nutrition check-ins")
    ci = q("SELECT date, est_calories, protein_g, alcohol_units, hunger FROM checkins ORDER BY date DESC LIMIT 14")
    if not ci.empty:
        st.dataframe(ci, use_container_width=True, hide_index=True)
    else:
        st.caption("Run `python checkin.py` each evening to log intake.")

st.divider()

# ---------------- Weekly insights ----------------
st.subheader("📊 Weekly insights")
icons = {"good": "✅", "warn": "⚠️", "info": "ℹ️"}
cards = insights.compute()
if cards:
    for row_start in range(0, len(cards), 2):
        cols = st.columns(2)
        for col, card in zip(cols, cards[row_start:row_start + 2]):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{icons.get(card['tone'],'')} {card['title']}**")
                    st.markdown(f"#### {card['headline']}")
                    st.caption(card["detail"])
else:
    st.caption("Not enough data for insights yet — they populate as history grows.")

st.caption(f"DB: {DB_PATH}")
