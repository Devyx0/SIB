import os
import sys
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from drive_pipeline.fiches_techniques.links import FICHES

SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_FILE = "token.json"
LINKS_FILE = "drive_pipeline/fiches_techniques/links.py"
EN_FOLDER = "1LNSnkRSOL1n_ayNcvHZn_Ty3vHqn8Bsw"
FR_FOLDER = "1hBhdwgrDmgkFmBqxuVtlfxcdDENlCsn5"
SUBFOLDER = "01-Old Technical Sheets"


def get_service():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def get_meta(service, file_id):
    m = service.files().get(fileId=file_id, fields="parents,name").execute()
    return m.get("parents", [None])[0], m.get("name", "")


def main():
    service = get_service()
    entries = [f for f in FICHES if f["subfolder"] == SUBFOLDER]
    print(f"Verifying {len(entries)} entries (2 API calls each)...\n")

    clean = []
    anomalies = []

    for i, f in enumerate(entries, 1):
        fr_id = f["french_drive_id"]
        en_id = f["english_drive_id"]

        fr_parent, fr_title = get_meta(service, fr_id)
        en_parent, en_title = get_meta(service, en_id)

        fr_ok = fr_parent == EN_FOLDER
        en_ok = en_parent == FR_FOLDER

        if fr_ok and en_ok:
            clean.append((f, fr_id, en_id, fr_title, en_title))
        else:
            anomalies.append({
                "name": f["english_name"],
                "fr_id": fr_id, "fr_parent": fr_parent, "fr_ok": fr_ok,
                "en_id": en_id, "en_parent": en_parent, "en_ok": en_ok,
            })

        if i % 20 == 0:
            print(f"  {i}/{len(entries)} verified...")

    print(f"\n{len(clean)} clean swap(s), {len(anomalies)} anomal(y/ies)\n")

    if anomalies:
        print("--- ANOMALIES (not swapped) ---")
        for a in anomalies:
            print(f"  {a['name']!r}")
            if not a["fr_ok"]:
                print(f"    french_drive_id  {a['fr_id']}  parent={a['fr_parent']}  (expected EN {EN_FOLDER})")
            if not a["en_ok"]:
                print(f"    english_drive_id {a['en_id']}  parent={a['en_parent']}  (expected FR {FR_FOLDER})")
        print()

    if not clean:
        print("Nothing to swap.")
        return

    # Apply swaps in-place to links.py using temp-placeholder pattern
    with open(LINKS_FILE, encoding="utf-8") as fh:
        text = fh.read()

    for f, old_fr, old_en, _, _ in clean:
        old_fr_lnk = f"https://drive.google.com/file/d/{old_fr}/view"
        old_en_lnk = f"https://drive.google.com/file/d/{old_en}/view"
        text = (text
            .replace(f'"french_drive_id": \'{old_fr}\'',     f'"french_drive_id": \'__SWAPID__\'')
            .replace(f'"english_drive_id": \'{old_en}\'',    f'"english_drive_id": \'{old_fr}\'')
            .replace(f'"french_drive_id": \'__SWAPID__\'',   f'"french_drive_id": \'{old_en}\'')
            .replace(f'"french_drive_link": \'{old_fr_lnk}\'',  f'"french_drive_link": \'__SWAPLNK__\'')
            .replace(f'"english_drive_link": \'{old_en_lnk}\'', f'"english_drive_link": \'{old_fr_lnk}\'')
            .replace(f'"french_drive_link": \'__SWAPLNK__\'',    f'"french_drive_link": \'{old_en_lnk}\'')
        )

    with open(LINKS_FILE, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"Swapped {len(clean)} entries in {LINKS_FILE}\n")

    # Spot-check using titles already fetched during verification
    # After swap: french_drive_id = old_en_id (FR folder file), english_drive_id = old_fr_id (EN folder file)
    # old_en_title = Drive title of old_en_id (FR folder file) -> should match french_name
    # old_fr_title = Drive title of old_fr_id (EN folder file) -> should match english_name
    print("--- SPOT-CHECK (first 10 entries) ---")
    for f, old_fr, old_en, old_fr_title, old_en_title in clean[:10]:
        new_fr_title = old_en_title   # Drive title of what is now french_drive_id
        new_en_title = old_fr_title   # Drive title of what is now english_drive_id

        fr_match = new_fr_title == f["french_name"]
        en_match = new_en_title == f["english_name"]
        status = "OK" if (fr_match and en_match) else "PARTIAL" if (fr_match or en_match) else "MISMATCH"
        print(f"  [{status}] {f['english_name']!r}")
        if not fr_match:
            print(f"    FR drive: {new_fr_title!r}")
            print(f"    FR fiches:{f['french_name']!r}")
        if not en_match:
            print(f"    EN drive: {new_en_title!r}")
            print(f"    EN fiches:{f['english_name']!r}")


if __name__ == "__main__":
    main()
