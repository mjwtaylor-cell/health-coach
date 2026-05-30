"""One-time Strava OAuth. Run once after adding CLIENT_ID/SECRET to .env.

    python strava_auth.py

It prints an authorize URL. You open it, click "Authorize", and your browser
lands on a localhost page that won't load — that's expected. Copy the `code`
value from the address bar and paste it here. The script exchanges it for a
long-lived refresh token and writes it back into .env. Done once, forever.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

from config import ROOT, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET

SCOPE = "activity:read_all"
REDIRECT = "http://localhost"


def main() -> None:
    if not (STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET):
        print("Add STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET to .env first.")
        return

    auth_url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={STRAVA_CLIENT_ID}&response_type=code&redirect_uri={REDIRECT}"
        f"&approval_prompt=force&scope={SCOPE}"
    )
    print("\n1) Open this URL in your browser and click Authorize:\n")
    print(f"   {auth_url}\n")
    print("2) Your browser will redirect to a localhost page that won't load — that's fine.")
    print("   Copy the whole address-bar URL (or just the code= value) and paste below.\n")

    pasted = input("Paste the redirect URL or code: ").strip()
    if "code=" in pasted:
        code = parse_qs(urlparse(pasted).query).get("code", [""])[0]
    else:
        code = pasted
    code = re.sub(r"[^A-Za-z0-9]", "", code)

    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": STRAVA_CLIENT_ID, "client_secret": STRAVA_CLIENT_SECRET,
        "code": code, "grant_type": "authorization_code",
    }, timeout=30)
    resp.raise_for_status()
    refresh = resp.json()["refresh_token"]

    env = Path(ROOT / ".env")
    text = env.read_text()
    if re.search(r"^STRAVA_REFRESH_TOKEN=.*$", text, flags=re.M):
        text = re.sub(r"^STRAVA_REFRESH_TOKEN=.*$", f"STRAVA_REFRESH_TOKEN={refresh}", text, flags=re.M)
    else:
        text += f"\nSTRAVA_REFRESH_TOKEN={refresh}\n"
    env.write_text(text)
    print("\n✅ Saved STRAVA_REFRESH_TOKEN to .env. Run `python pipeline.py` to pull your runs.")


if __name__ == "__main__":
    main()
