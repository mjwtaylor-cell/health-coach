# Free deploy (no credit card) — Streamlit Community Cloud + Turso

Result: a private `https://…streamlit.app` URL you open on your phone, $0, no card.
All three services log in **with your GitHub account**.

- **GitHub** — holds the code
- **Turso** — free hosted SQLite, keeps your check-ins durable
- **Streamlit Community Cloud (SCC)** — runs the dashboard, free, with email-restricted login

Your `.env` is gitignored, so no secrets ever go into the repo — they live in SCC's
encrypted secrets manager.

---

## Step 1 — GitHub (you create the account + repo)
1. Make a free account at https://github.com if you don't have one.
2. Create a new **private** repo called `health-coach` (don't initialize with anything).
3. Back here, I'll push the code to it (or run these yourself):
   ```bash
   cd ~/projects/health-coach
   git remote add origin https://github.com/<your-username>/health-coach.git
   git push -u origin main
   ```

## Step 2 — Turso (free database, no card)
1. Sign up at https://turso.tech (log in with GitHub).
2. Create a database (dashboard → **Create Database**, any name, pick a nearby region).
3. Copy two values:
   - the **Database URL** (looks like `libsql://your-db-xxxx.turso.io`)
   - an **auth token** (Create Token button)
4. Hold onto both for Step 3.

## Step 3 — Streamlit Community Cloud (free host + login)
1. Go to https://share.streamlit.io and sign in with GitHub.
2. **New app** → pick your `health-coach` repo → main file `dashboard.py` → Deploy.
3. In **Advanced settings → Secrets**, paste this (TOML), filling in your values:
   ```toml
   OURA_TOKEN = "…"
   STRAVA_CLIENT_ID = "…"
   STRAVA_CLIENT_SECRET = "…"
   STRAVA_REFRESH_TOKEN = "…"
   EIGHTSLEEP_EMAIL = "…"
   EIGHTSLEEP_PASSWORD = "…"
   TURSO_DATABASE_URL = "libsql://your-db-xxxx.turso.io"
   TURSO_AUTH_TOKEN = "…"
   APP_PASSWORD = "choose-a-strong-password"
   AUTO_REFRESH = "1"
   ```
   (I can generate this block pre-filled from your `.env` — just ask.)
4. **Make it private:** app settings → **Sharing** → restrict viewers to your Google email.

## Step 4 — On your phone
1. Open the `…streamlit.app` URL in Safari → enter your `APP_PASSWORD`.
2. Share → **Add to Home Screen** for an app icon.
3. First open backfills history from the APIs; check-ins persist in Turso.

---

### Notes
- **Sleeps when idle:** SCC apps nap after inactivity and wake on open (a few seconds). Fine for daily use.
- **Auto-refresh:** opening the app pulls fresh data if it's >3h old — no scheduler needed.
- The local Mac version still works unchanged (it ignores Turso unless the URL is set).
