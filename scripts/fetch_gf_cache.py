"""
scripts/fetch_gf_cache.py — Targeted read-only fetch of the 148 gravity_forms
calendar events by their stored event_id. Saves raw HTML descriptions to
work/gf_raw_events_cache.json (gitignored — contains tenant PII).

    uv run python scripts/fetch_gf_cache.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import psycopg2
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TOKEN_PATH = ROOT / "token.json"
CREDS_PATH = ROOT / "credentials.json"
OUT_PATH   = ROOT / "work" / "gf_raw_events_cache.json"


def get_conn():
    return psycopg2.connect(
        host="localhost", port=54322,
        user="postgres", password="postgres", dbname="postgres",
    )


def get_creds() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
            return creds
        except (RefreshError, Exception):
            # Token revoked — delete it and re-auth below
            TOKEN_PATH.unlink(missing_ok=True)
            creds = None

    # Full OAuth flow (opens browser)
    if not CREDS_PATH.exists():
        raise FileNotFoundError(f"credentials.json not found at {CREDS_PATH}")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    return creds


def main():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT request_id, event_id, source_calendar_id
        FROM maintenance_request
        WHERE body_format = 'gravity_forms'
        ORDER BY request_id
    """)
    rows = cur.fetchall()
    conn.close()
    print(f"Events to fetch: {len(rows)}")

    creds   = get_creds()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    fetched = []
    missing = []
    errors  = []

    for i, (request_id, event_id, cal_id) in enumerate(rows, 1):
        if i % 20 == 0:
            print(f"  {i}/{len(rows)}...", flush=True)
        try:
            ev = service.events().get(calendarId=cal_id, eventId=event_id).execute()
            fetched.append({
                "request_id":  request_id,
                "event_id":    event_id,
                "calendar_id": cal_id,
                "title":       ev.get("summary", ""),
                "description": ev.get("description", "") or "",
            })
        except Exception as e:
            msg = str(e)
            if "404" in msg or "notFound" in msg.lower() or "410" in msg:
                missing.append({"request_id": request_id, "event_id": event_id,
                                 "reason": "deleted_or_not_found"})
            else:
                errors.append({"request_id": request_id, "event_id": event_id,
                                "error": msg[:200]})

    cache = {
        "fetched": len(fetched),
        "missing": missing,
        "errors":  errors,
        "events":  fetched,
    }
    OUT_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    print(f"\nFetched : {len(fetched)}/{len(rows)}")
    print(f"Missing : {len(missing)} — {[m['request_id'] for m in missing]}")
    print(f"Errors  : {len(errors)}  — {[e['request_id'] for e in errors]}")
    print(f"Saved   → {OUT_PATH}")


if __name__ == "__main__":
    main()
