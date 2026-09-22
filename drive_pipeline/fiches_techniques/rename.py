"""
rename.py — Execute English-variant Fiches Techniques renames on Google Drive.

Auth: OAuth via credentials.json (Desktop App from Google Cloud Console).
      First run opens a browser. Token cached to token.json afterwards.

Run: uv run rename.py
"""

import os
import sys
import unicodedata
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from mapping import (
    RENAMES_ROOT,
    RENAMES_EMPLOI,
    RENAMES_BOITE,
    RENAMES_ANCIENNE,
    RENAMES_ARCHIVES,
)

SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")
CREDS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")

FOLDERS = {
    "root":     "1IGi8xO444ZHVr7i_biaHNneOXo1du_Cx",
    "emploi":   "1X1CJGWvlIWRd1721LJWy7SmsJ3AsNRTb",
    "boite":    "14_Ot9Cj5gxZWlw1ckcB_IL1amvh8QcxT",
    "ancienne": "1LNSnkRSOL1n_ayNcvHZn_Ty3vHqn8Bsw",
    "archives": "1DqTZMes9tchINlNyZUAxOcUwDLoSBKHv",
}


def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def _paginate(service, folder_id):
    page_token = None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token,
            pageSize=1000,
        ).execute()
        yield from resp.get("files", [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def list_children(service, folder_id):
    return {_nfc(f["name"]): f["id"] for f in _paginate(service, folder_id)}


def list_subtree(service, folder_id):
    result = {}
    for f in _paginate(service, folder_id):
        if f["mimeType"] == "application/vnd.google-apps.folder":
            result.update(list_subtree(service, f["id"]))
        else:
            result[_nfc(f["name"])] = f["id"]
    return result


def apply_renames(service, renames: dict, name_to_id: dict, label: str):
    ok = skipped = 0
    for old, new in renames.items():
        file_id = name_to_id.get(_nfc(old))
        if file_id is None:
            print(f"  MISSING  [{label}] {old!r}")
            skipped += 1
            continue
        updated = service.files().update(
            fileId=file_id,
            body={"name": new},
            fields="id, name",
        ).execute()
        if updated.get("name") == new:
            print(f"  OK       [{label}] {old!r}  →  {new!r}")
            ok += 1
        else:
            print(f"  ERROR    [{label}] API returned {updated.get('name')!r}, expected {new!r}")
            sys.exit(1)
    return ok, skipped


def main():
    if not os.path.exists(CREDS_FILE):
        print(f"ERROR: {CREDS_FILE} not found.")
        print("Download an OAuth Desktop App credential from Google Cloud Console.")
        sys.exit(1)

    service = get_service()
    total_ok = total_skip = 0

    sections = [
        ("root",     RENAMES_ROOT,     list_children),
        ("boite",    RENAMES_BOITE,    list_children),
        ("ancienne", RENAMES_ANCIENNE, list_children),
        ("archives", RENAMES_ARCHIVES, list_children),
        ("emploi",   RENAMES_EMPLOI,   list_subtree),
    ]

    for key, renames, lister in sections:
        n = len(renames)
        print(f"\n=== {key.upper()} ({n} renames) ===")
        name_to_id = lister(service, FOLDERS[key])
        ok, skip = apply_renames(service, renames, name_to_id, key)
        total_ok += ok
        total_skip += skip

    print(f"\nDone. {total_ok} renamed, {total_skip} not found (already renamed or missing).")


if __name__ == "__main__":
    main()
