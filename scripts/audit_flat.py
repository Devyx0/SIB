import os
import sys
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from drive_pipeline.fiches_techniques.links import FICHES

SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")

EXPECTED_FOLDER_IDS = {
    "User Guides ／ Links":   "1X1CJGWvlIWRd1721LJWy7SmsJ3AsNRTb",
    "01-Old Technical Sheets": "1LNSnkRSOL1n_ayNcvHZn_Ty3vHqn8Bsw",
    "00-Archives":             "1DqTZMes9tchINlNyZUAxOcUwDLoSBKHv",
    "Logisco Key Box List":    "14_Ot9Cj5gxZWlw1ckcB_IL1amvh8QcxT",
}

def get_service():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)

def main():
    service = get_service()
    mismatches = []
    checked = 0

    flat_entries = [(f, f["subfolder"]) for f in FICHES if f["subfolder"] in EXPECTED_FOLDER_IDS]
    print(f"Checking {len(flat_entries)} flat-labeled entries...")

    for fiche, subfolder in flat_entries:
        expected_parent = EXPECTED_FOLDER_IDS[subfolder]
        file_id = fiche["english_drive_id"]
        if not file_id:
            print(f"  SKIP (no english_drive_id): {fiche['english_name']!r}")
            continue

        meta = service.files().get(fileId=file_id, fields="id, name, parents").execute()
        parents = meta.get("parents", [])
        checked += 1

        if expected_parent not in parents:
            mismatches.append({
                "english_name": fiche["english_name"],
                "subfolder": subfolder,
                "expected_parent": expected_parent,
                "actual_parents": parents,
                "file_id": file_id,
            })
            print(f"  MISMATCH: {fiche['english_name']!r}")
            print(f"    subfolder label: {subfolder!r}")
            print(f"    expected parent: {expected_parent}")
            print(f"    actual parents:  {parents}")
        else:
            print(f"  OK: {fiche['english_name']!r}")

    print(f"\n=== {checked} checked, {len(mismatches)} mismatches ===")
    if mismatches:
        sys.exit(1)

if __name__ == "__main__":
    main()
