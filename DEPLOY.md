# Deploying Health Coach to the cloud (phone-primary)

Goal: a private HTTPS URL you open on your phone, working whether or not your Mac is on.
Recommended host: **Fly.io** (persistent storage, always-available, one account, secrets built in).

## What runs in the cloud
- The Streamlit dashboard (+ login gate + check-in form)
- A persistent SQLite DB on a Fly **volume** (`/data`) — survives restarts
- **Auto-refresh on open**: opening the app pulls fresh Oura/Strava/Eight Sleep data if >3h stale (no separate scheduler needed)

Your Strava refresh token already works from the cloud — the `localhost` callback only mattered for the one-time authorize you already did.

## One-time setup (the parts only you can do)
1. **Create a Fly.io account:** https://fly.io/app/sign-up  (needs a card; a tiny always-on app is ~$2–3/mo, often within the free allowance since it sleeps when idle)
2. **Install the CLI:**  `brew install flyctl`  (or `curl -L https://fly.io/install.sh | sh`)
3. **Log in:**  `fly auth login`

Then tell me you're logged in — I can run the rest from here, or you can:

## Deploy
```bash
cd ~/projects/health-coach

# 1. Create the app (pick a unique name; updates fly.toml)
fly launch --no-deploy --copy-config --name my-health-coach --region iad

# 2. Create the persistent volume for the database
fly volumes create health_data --size 1 --region iad --yes

# 3. Set your secrets (encrypted — never stored in the repo)
fly secrets set \
  OURA_TOKEN="$(grep ^OURA_TOKEN .env | cut -d= -f2)" \
  STRAVA_CLIENT_ID="$(grep ^STRAVA_CLIENT_ID .env | cut -d= -f2)" \
  STRAVA_CLIENT_SECRET="$(grep ^STRAVA_CLIENT_SECRET .env | cut -d= -f2)" \
  STRAVA_REFRESH_TOKEN="$(grep ^STRAVA_REFRESH_TOKEN .env | cut -d= -f2)" \
  EIGHTSLEEP_EMAIL="$(grep ^EIGHTSLEEP_EMAIL .env | cut -d= -f2)" \
  EIGHTSLEEP_PASSWORD="$(grep ^EIGHTSLEEP_PASSWORD .env | cut -d= -f2)" \
  APP_PASSWORD="choose-a-strong-password"

# 4. Deploy
fly deploy
```

`fly deploy` prints your URL (e.g. `https://my-health-coach.fly.dev`).

## On your phone
1. Open the URL in Safari → enter your `APP_PASSWORD`
2. Share button → **Add to Home Screen** → you get an app icon
3. First open backfills your history from the APIs (Oura ~30d, Strava ~60d)

## Updating later
Edit code on your Mac, then `fly deploy` again. (Your data on the volume is untouched.)

## Strictly-$0 alternative
Streamlit Community Cloud is free and has the best built-in auth (restrict viewers to your
Google email), but its filesystem is ephemeral — your check-ins would need an external DB
(e.g. Turso, free) to survive restarts. More moving parts; ask if you want this route instead.
