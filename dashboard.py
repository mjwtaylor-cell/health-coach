"""Health Coach — dark, premium dashboard. Local: .venv/bin/streamlit run dashboard.py

Set APP_PASSWORD (env or st.secrets) to require login; unset = open locally.
"""
from __future__ import annotations

import datetime as dt
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import streamlit.components.v1 as components

import config
import insights
import planner
from db import init_db, query_df, upsert

_ICON = "static/icon.png"
st.set_page_config(page_title="Health Coach",
                   page_icon=_ICON if os.path.exists(_ICON) else "🏃",
                   layout="wide", initial_sidebar_state="collapsed")


def _pwa_head() -> None:
    """Inject home-screen icon + standalone meta into the parent <head> (Streamlit has no head API)."""
    components.html("""
    <script>
    const d = window.parent.document;
    const set = (sel, tag, attrs) => { let e = d.head.querySelector(sel);
      if(!e){ e = d.createElement(tag); d.head.appendChild(e); }
      Object.entries(attrs).forEach(([k,v]) => e.setAttribute(k,v)); };
    set("link[rel='apple-touch-icon']","link",{rel:"apple-touch-icon",href:"app/static/apple-touch-icon.png"});
    set("meta[name='apple-mobile-web-app-capable']","meta",{name:"apple-mobile-web-app-capable",content:"yes"});
    set("meta[name='apple-mobile-web-app-status-bar-style']","meta",{name:"apple-mobile-web-app-status-bar-style",content:"black-translucent"});
    set("meta[name='apple-mobile-web-app-title']","meta",{name:"apple-mobile-web-app-title",content:"Health Coach"});
    set("meta[name='theme-color']","meta",{name:"theme-color",content:"#0D0E12"});
    </script>
    """, height=0)

ACCENT = "#FF6A3D"
MUTED = "#8A8F99"
GRID = "#23262F"
CARD = "#16181F"
CALL = {"hard": "#FF5A4D", "moderate": "#FFA336", "easy": "#3DD68C", "rest": "#4AA8FF"}


# ---------------- auth gate ----------------
def _gate() -> None:
    pw = config.secret("APP_PASSWORD")
    if not pw or st.session_state.get("authed"):
        return
    st.markdown("<div style='height:18vh'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align:center'>🏃 Health Coach</h1>", unsafe_allow_html=True)
    c = st.columns([1, 2, 1])[1]
    entered = c.text_input("Password", type="password", label_visibility="collapsed", placeholder="Password")
    if entered and entered == pw:
        st.session_state["authed"] = True
        st.rerun()
    elif entered:
        c.error("Incorrect password.")
    st.stop()


_gate()
init_db()

if config.secret("AUTO_REFRESH") == "1":
    @st.cache_data(ttl=3 * 3600, show_spinner="Refreshing your latest data…")
    def _auto_pull() -> bool:
        import pipeline
        pipeline.run(days_back=14)
        return True
    _auto_pull()


# ---------------- styling ----------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html, body, [class*="css"], .stApp, button, input, textarea { font-family:'Inter',-apple-system,sans-serif; }
.stApp { background:
    radial-gradient(1200px 600px at 50% -200px, #1a1410 0%, #0D0E12 55%); }
#MainMenu, header[data-testid="stHeader"], footer { display:none !important; }
.block-container { padding:1.1rem 1rem 4rem; max-width:1080px; }
h1,h2,h3 { font-weight:800 !important; letter-spacing:-0.02em; }
[data-testid="stMetricValue"] { font-weight:800; }

.hc-hero { background:linear-gradient(135deg,#191b22 0%,#141318 100%);
    border:1px solid #262932; border-radius:22px; padding:22px 24px; margin-bottom:14px; }
.hc-badge { display:inline-flex; align-items:center; gap:8px; padding:7px 16px; border-radius:999px;
    font-weight:800; font-size:.95rem; letter-spacing:.06em; }
.hc-session { font-size:1.18rem; font-weight:600; color:#F4F5F7; line-height:1.45; margin:14px 0 6px; }
.hc-why { color:#8A8F99; font-size:.86rem; }

.hc-grid { display:flex; flex-wrap:wrap; gap:12px; margin:4px 0 8px; }
.hc-tile { flex:1 1 150px; background:#16181F; border:1px solid #23262F; border-radius:16px; padding:14px 16px; }
.hc-label { font-size:.7rem; letter-spacing:.1em; text-transform:uppercase; color:#8A8F99; font-weight:700; }
.hc-value { font-size:1.95rem; font-weight:800; color:#ECEDEF; line-height:1.15; margin-top:3px; }
.hc-unit { font-size:.95rem; font-weight:600; color:#8A8F99; }
.hc-sub { font-size:.76rem; color:#6f7681; margin-top:2px; }

.hc-sec { font-size:.78rem; letter-spacing:.14em; text-transform:uppercase; color:#8A8F99;
    font-weight:800; margin:22px 0 8px; }
.hc-ins { background:#16181F; border:1px solid #23262F; border-left-width:4px; border-radius:14px;
    padding:14px 16px; height:100%; }
.hc-ins h4 { margin:6px 0 4px; font-size:1.05rem; font-weight:800; color:#F4F5F7; }
.hc-ins .t { font-size:.7rem; letter-spacing:.08em; text-transform:uppercase; font-weight:700; }
.hc-ins p { color:#8A8F99; font-size:.84rem; margin:0; }
div[data-testid="stDataFrame"] { border-radius:14px; overflow:hidden; }
.stButton button { border-radius:12px; font-weight:700; border:1px solid #2a2d37; }
</style>
""", unsafe_allow_html=True)


_pwa_head()


def q(sql: str) -> pd.DataFrame:
    return query_df(sql)


def latest(df: pd.DataFrame, col: str):
    s = df[col].dropna() if (not df.empty and col in df) else pd.Series(dtype=float)
    return (s.iloc[-1] if len(s) else None), (round(s.tail(7).mean(), 1) if len(s) else None)


def series(df: pd.DataFrame, col: str, n: int = 14) -> list:
    if df.empty or col not in df:
        return []
    return df[col].dropna().tail(n).tolist()


def sparkline_svg(vals, color, w=132, h=34) -> str:
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = " ".join(f"{i/(n-1)*w:.1f},{h-3-(v-lo)/rng*(h-6):.1f}" for i, v in enumerate(vals))
    lx, ly = w, h - 3 - (vals[-1] - lo) / rng * (h - 6)
    return (f"<svg width='100%' height='{h}' viewBox='0 0 {w} {h}' preserveAspectRatio='none' style='margin-top:8px;display:block'>"
            f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/>"
            f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='2.8' fill='{color}'/></svg>")


def tile(label, value, unit="", sub="", color="#ECEDEF", spark=""):
    val = "—" if value is None else value
    return (f"<div class='hc-tile'><div class='hc-label'>{label}</div>"
            f"<div class='hc-value' style='color:{color}'>{val}<span class='hc-unit'> {unit}</span></div>"
            f"<div class='hc-sub'>{sub}</div>{spark}</div>")


def score_color(v, good, ok):
    if v is None:
        return "#ECEDEF"
    return "#3DD68C" if v >= good else ("#FFA336" if v >= ok else "#FF5A4D")


def style_fig(fig, color=ACCENT, height=230):
    fig.update_layout(height=height, margin=dict(l=6, r=6, t=8, b=6),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=MUTED, family="Inter", size=11), showlegend=False)
    fig.update_xaxes(showgrid=False, zeroline=False, title=None)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False, title=None)
    return fig


def line(df, x, y, color=ACCENT, fill=True, height=230):
    fig = go.Figure(go.Scatter(
        x=df[x], y=df[y], mode="lines", line=dict(color=color, width=2.4, shape="spline"),
        fill="tozeroy" if fill else None, fillcolor="rgba(255,106,61,0.10)" if color == ACCENT else "rgba(255,255,255,0.04)"))
    return style_fig(fig, color, height)


PLOT_CFG = {"displayModeBar": False}


# ---------------- data ----------------
plan = planner.make_plan()
zones = planner.hr_zones()
rec = q("SELECT date, score FROM readiness WHERE source='oura' ORDER BY date")
slp = q("SELECT date, total_min, hrv_avg, hr_low FROM sleep WHERE source='oura' ORDER BY date")
if not slp.empty:
    slp["hours"] = slp["total_min"] / 60

r_now, r_avg = latest(rec, "score")
h_now, h_avg = latest(slp, "hours")
v_now, v_avg = latest(slp, "hrv_avg")
rhr_now, rhr_avg = latest(slp, "hr_low")

# this-week aggregates
_monday = (dt.date.today() - dt.timedelta(days=dt.date.today().weekday())).isoformat()
_agg = q(f"SELECT COALESCE(SUM(duration_min),0) mins, COALESCE(SUM(distance_km),0) km FROM workouts WHERE date>='{_monday}'")
wk_mins = float(_agg["mins"].iloc[0]) if not _agg.empty else 0
wk_km = float(_agg["km"].iloc[0]) if not _agg.empty else 0
_wk_slp = slp[slp["date"] >= _monday] if not slp.empty else slp
wk_sleep = round(_wk_slp["hours"].mean(), 1) if (not _wk_slp.empty and "hours" in _wk_slp) else None
wk_runs = planner._runs_this_week()


# ---------------- check-in modal ----------------
@st.dialog("🌙 Evening check-in")
def checkin_dialog():
    today_iso = dt.date.today().isoformat()
    if not q(f"SELECT 1 FROM checkins WHERE date='{today_iso}'").empty:
        st.caption("Already logged today — resubmit to update.")
    cals = st.number_input("Calories", 0, 8000, step=50, value=None, placeholder="rough estimate")
    protein = st.number_input("Protein (g)", 0, 400, step=5, value=None, placeholder="grams")
    alcohol = st.number_input("Alcohol (units)", 0.0, 20.0, step=1.0, value=0.0)
    hunger = st.slider("Hunger", 1, 5, 3, help="1 = stuffed, 5 = ravenous")
    notes = st.text_input("Notes", placeholder="stress, soreness, anything")
    if st.button("Save & plan tomorrow", use_container_width=True, type="primary"):
        upsert("checkins", [{"date": today_iso, "est_calories": cals, "protein_g": protein,
                             "alcohol_units": alcohol, "hunger": hunger, "notes": notes}])
        tplan = planner.make_plan(dt.date.today() + dt.timedelta(days=1))
        upsert("plans", [tplan])
        st.success(f"Saved. Tomorrow: {tplan['training_call'].upper()} — {tplan['session']}")


# ---------------- header ----------------
hc, hb = st.columns([3, 1])
hc.markdown(f"<h1 style='margin-bottom:0'>🏃 Health Coach</h1>"
            f"<div style='color:{MUTED};font-size:.9rem'>{dt.date.today():%A, %B %-d}</div>",
            unsafe_allow_html=True)
hb.write("")
if hb.button("＋ Check-in", use_container_width=True):
    checkin_dialog()

# ---------------- today hero ----------------
c = plan["training_call"]
badge_c = CALL.get(c, ACCENT)
fuel = (f"&nbsp;·&nbsp; <b style='color:{ACCENT}'>{plan['calorie_target']:.0f}</b> kcal &nbsp; "
        f"<b style='color:{ACCENT}'>{plan['protein_target']:.0f}</b> g protein") if plan["calorie_target"] else ""
st.markdown(
    f"<div class='hc-hero'>"
    f"<span class='hc-label'>Today's call</span> {fuel}"
    f"<div style='margin:8px 0'><span class='hc-badge' style='background:{badge_c}1f;color:{badge_c};border:1px solid {badge_c}55'>"
    f"● {c.upper()}</span></div>"
    f"<div class='hc-session'>{plan['session']}</div>"
    f"<div class='hc-why'>{plan['rationale']}</div></div>",
    unsafe_allow_html=True)

# ---------------- this week ----------------
st.markdown(
    "<div class='hc-sec'>This week</div><div class='hc-grid'>"
    + tile("Runs", f"{wk_runs}/3", "", "target 3", ACCENT if wk_runs < 3 else "#3DD68C")
    + tile("Training", round(wk_mins), "min", "logged")
    + tile("Distance", round(wk_km, 1), "km", "run · ride · walk")
    + tile("Avg sleep", wk_sleep, "h", "this week", score_color(wk_sleep, 7.5, 6.5))
    + "</div>", unsafe_allow_html=True)

# ---------------- recovery snapshot (now, with sparklines) ----------------
st.markdown(
    "<div class='hc-sec'>Recovery</div><div class='hc-grid'>"
    + tile("Readiness", None if r_now is None else round(r_now), "", f"7-day avg {r_avg}" if r_avg else "—",
           score_color(r_now, 80, 65), sparkline_svg(series(rec, "score"), score_color(r_now, 80, 65)))
    + tile("Sleep", None if h_now is None else round(h_now, 1), "h", f"7-day avg {h_avg} h" if h_avg else "—",
           score_color(h_now, 7.5, 6.5), sparkline_svg(series(slp, "hours"), score_color(h_now, 7.5, 6.5)))
    + tile("HRV", None if v_now is None else round(v_now), "ms", f"7-day avg {round(v_avg) if v_avg else '—'} ms",
           "#4AA8FF", sparkline_svg(series(slp, "hrv_avg"), "#4AA8FF"))
    + tile("Resting HR", None if rhr_now is None else round(rhr_now), "bpm", f"7-day avg {round(rhr_avg) if rhr_avg else '—'} bpm",
           "#3DD68C", sparkline_svg(series(slp, "hr_low"), "#3DD68C"))
    + "</div>", unsafe_allow_html=True)

# ---------------- recovery ----------------
if not rec.empty:
    st.markdown("<div class='hc-sec'>Trends</div>", unsafe_allow_html=True)
    a, b = st.columns(2)
    rfig = go.Figure(go.Scatter(x=rec["date"], y=rec["score"], mode="lines",
                                line=dict(color="#ECEDEF", width=2.4, shape="spline")))
    rfig.add_hrect(y0=0, y1=65, fillcolor="#FF5A4D", opacity=0.10, line_width=0, layer="below")
    rfig.add_hrect(y0=65, y1=80, fillcolor="#FFA336", opacity=0.10, line_width=0, layer="below")
    rfig.add_hrect(y0=80, y1=100, fillcolor="#3DD68C", opacity=0.12, line_width=0, layer="below")
    style_fig(rfig); rfig.update_yaxes(range=[0, 100])
    a.markdown("<div class='hc-label'>Readiness · zones</div>", unsafe_allow_html=True)
    a.plotly_chart(rfig, use_container_width=True, config=PLOT_CFG)
    if not slp.empty:
        b.markdown("<div class='hc-label'>Sleep (hours)</div>", unsafe_allow_html=True)
        bar = go.Figure(go.Bar(x=slp["date"], y=slp["hours"], marker_color=ACCENT, marker_line_width=0))
        b.plotly_chart(style_fig(bar), use_container_width=True, config=PLOT_CFG)
        a2, b2 = st.columns(2)
        a2.markdown("<div class='hc-label'>HRV (ms)</div>", unsafe_allow_html=True)
        a2.plotly_chart(line(slp, "date", "hrv_avg", "#4AA8FF", fill=False), use_container_width=True, config=PLOT_CFG)
        b2.markdown("<div class='hc-label'>Resting HR (bpm)</div>", unsafe_allow_html=True)
        b2.plotly_chart(line(slp, "date", "hr_low", "#3DD68C", fill=False), use_container_width=True, config=PLOT_CFG)

# ---------------- training load ----------------
wk = q("SELECT date, type, source, duration_min, distance_km, hr_avg FROM workouts ORDER BY date DESC LIMIT 20")
st.markdown("<div class='hc-sec'>Training load</div>", unsafe_allow_html=True)
runs_done = planner._runs_this_week()
st.markdown("<div class='hc-grid'>"
            + tile("Runs this week", f"{runs_done} / 3", "", "target 3", ACCENT if runs_done < 3 else "#3DD68C")
            + (tile("Last 20 sessions", len(wk), "", "across all sources") if not wk.empty else "")
            + "</div>", unsafe_allow_html=True)
if not wk.empty:
    st.dataframe(wk, use_container_width=True, hide_index=True,
                 column_config={"duration_min": "min", "distance_km": "km", "hr_avg": "avg HR"})

# ---------------- insights ----------------
st.markdown("<div class='hc-sec'>Weekly insights</div>", unsafe_allow_html=True)
tone_c = {"good": "#3DD68C", "warn": "#FFA336", "info": "#4AA8FF"}
cards = insights.compute()
for i in range(0, len(cards), 2):
    cols = st.columns(2)
    for col, card in zip(cols, cards[i:i + 2]):
        cc = tone_c.get(card["tone"], MUTED)
        col.markdown(
            f"<div class='hc-ins' style='border-left-color:{cc}'>"
            f"<div class='t' style='color:{cc}'>{card['title']}</div>"
            f"<h4>{card['headline']}</h4><p>{card['detail']}</p></div>",
            unsafe_allow_html=True)

# ---------------- diagnostic footer ----------------
import db as _dbmod  # noqa: E402
_src = "Turso ☁" if _dbmod._use_turso() else "local (ephemeral)"
_rn = q("SELECT COUNT(*) c FROM readiness")
_cnt = int(_rn["c"].iloc[0]) if not _rn.empty else 0
st.caption(f"data source: {_src} · {_cnt} readiness rows · {len(wk) if not wk.empty else 0} recent workouts")
