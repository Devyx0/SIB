"""
Task 1: Determine actual xlsx cell layout for one file from each subfolder.
Downloads 3 files via Drive API and prints raw shape + first cells.
"""
import io
import os
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload
from drive_pipeline.fiches_techniques.links import FICHES

SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_FILE = "token.json"
TARGETS = ["root", "01-Old Technical Sheets", "00-Archives"]


def get_service():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def download_bytes(service, file_id):
    buf = io.BytesIO()
    req = service.files().get_media(fileId=file_id)
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.seek(0)
    return buf


def main():
    service = get_service()

    # Pick one xlsx file from each target subfolder
    samples = {}
    for sf in TARGETS:
        for f in FICHES:
            if f["subfolder"] == sf and f["french_name"].endswith(".xlsx"):
                samples[sf] = f
                break

    known_labels = ["ACCÈS", "Année de construction", "Nb de logements", "Logements"]

    for sf, fiche in samples.items():
        file_id = fiche["french_drive_id"]
        print(f"\n{'='*60}")
        print(f"Subfolder : {sf!r}")
        print(f"File      : {fiche['french_name']!r}")
        print(f"Drive ID  : {file_id}")

        buf = download_bytes(service, file_id)
        df = pd.read_excel(buf, header=None, engine="openpyxl")
        print(f"Shape     : {df.shape}  (rows x cols)")

        print("\nFirst 6 rows, first 6 columns (raw):")
        print(df.iloc[:6, :6].to_string())

        # Search for known labels
        print("\nKnown-label search:")
        for label in known_labels:
            found = []
            for r in range(min(df.shape[0], 60)):
                for c in range(min(df.shape[1], 60)):
                    val = df.iat[r, c]
                    if isinstance(val, str) and label in val:
                        found.append(f"  ({r},{c}) = {val!r}")
            if found:
                for loc in found:
                    print(f"  '{label}' at{loc}")
            else:
                print(f"  '{label}' — not found in first 60x60")


if __name__ == "__main__":
    main()
