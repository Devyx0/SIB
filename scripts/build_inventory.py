"""
Tasks 2 & 3: Download all 350 Fiches Techniques xlsx files, extract field labels
(col 0, skip row 0 and NaN rows), write columns_inventory.py, then cluster and report.
"""
import io
import os
import sys
import threading
import concurrent.futures
from collections import defaultdict
from googleapiclient.discovery import build
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
from drive_pipeline.fiches_techniques.links import FICHES

SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_FILE = "token.json"
OUT_FILE = "columns_inventory.py"
TARGET_SUBFOLDERS = {"root", "01-Old Technical Sheets", "00-Archives"}
MAX_WORKERS = 8

_tls = threading.local()


def get_service():
    # One service object per thread (httplib2 is not thread-safe)
    if not hasattr(_tls, "service"):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        _tls.service = build("drive", "v3", credentials=creds)
    return _tls.service


def download_bytes(service, file_id):
    buf = io.BytesIO()
    req = service.files().get_media(fileId=file_id)
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.seek(0)
    return buf


def extract_labels(buf):
    df = pd.read_excel(buf, header=None, engine="openpyxl")
    col0 = df.iloc[1:, 0]  # skip row 0 (address)
    labels = [str(v).strip() for v in col0 if pd.notna(v) and str(v).strip()]
    return labels


def process_one(fiche):
    service = get_service()
    file_id = fiche["french_drive_id"]
    try:
        buf = download_bytes(service, file_id)
        labels = extract_labels(buf)
        return {
            "english_name": fiche["english_name"],
            "subfolder": fiche["subfolder"],
            "labels": labels,
            "label_count": len(labels),
        }
    except Exception as exc:
        return {
            "english_name": fiche["english_name"],
            "subfolder": fiche["subfolder"],
            "labels": None,
            "label_count": -1,
            "_error": str(exc),
        }


def main():
    targets = [
        f for f in FICHES
        if f["subfolder"] in TARGET_SUBFOLDERS and f["english_name"].endswith(".xlsx")
    ]
    print(f"{len(targets)} files to process")

    results = [None] * len(targets)
    done_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_to_idx = {pool.submit(process_one, t): i for i, t in enumerate(targets)}
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            results[idx] = future.result()
            done_count += 1
            if done_count % 50 == 0:
                print(f"  {done_count}/{len(targets)} done...")

    errors = [r for r in results if r.get("_error")]
    if errors:
        print(f"\n{len(errors)} ERRORS:")
        for e in errors:
            print(f"  {e['english_name']!r}: {e['_error']}")

    clean = [r for r in results if not r.get("_error")]
    print(f"\n{len(clean)} successful, {len(errors)} errors")

    # Write columns_inventory.py
    lines = ["INVENTORY = [\n"]
    for r in clean:
        labels_repr = repr(r["labels"])
        lines.append(
            f"    {{'english_name': {r['english_name']!r}, "
            f"'subfolder': {r['subfolder']!r}, "
            f"'labels': {labels_repr}, "
            f"'label_count': {r['label_count']}}},\n"
        )
    lines.append("]\n")
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    print(f"Wrote {OUT_FILE}")

    # ── TASK 3: Cluster by exact labels tuple ──────────────────────────────
    print("\n" + "="*60)
    print("CLUSTER REPORT")
    print("="*60)

    clusters = defaultdict(list)
    for r in clean:
        key = tuple(r["labels"])
        clusters[key].append(r)

    # Sort clusters by size descending
    sorted_clusters = sorted(clusters.items(), key=lambda kv: -len(kv[1]))

    print(f"\n{len(clusters)} distinct label-set(s) found\n")

    for rank, (key, members) in enumerate(sorted_clusters, 1):
        subfolders = sorted({m["subfolder"] for m in members})
        label_counts = sorted({m["label_count"] for m in members})
        print(f"Cluster {rank}: {len(members)} file(s), {len(key)} label(s), subfolder(s): {subfolders}")
        print(f"  Label count(s) in cluster: {label_counts}")
        print(f"  Files:")
        for m in members[:5]:
            print(f"    {m['english_name']!r}")
        if len(members) > 5:
            print(f"    ... and {len(members)-5} more")
        print(f"  Labels:")
        for lbl in key:
            print(f"    {lbl!r}")
        print()

    # Near-match analysis: files whose label set isn't in the top-2 clusters
    top2_keys = {k for k, _ in sorted_clusters[:2]}
    outliers = [r for r in clean if tuple(r["labels"]) not in top2_keys]
    if outliers:
        print(f"\nOUTLIERS (not in top-2 clusters): {len(outliers)} file(s)")
        for o in outliers:
            print(f"  {o['english_name']!r}  [{o['subfolder']}]  ({o['label_count']} labels)")
            # Show diff vs nearest top cluster
            nearest_key = min(top2_keys, key=lambda k: abs(len(k) - len(o["labels"])))
            o_set = set(o["labels"])
            n_set = set(nearest_key)
            only_in_file = sorted(o_set - n_set)
            only_in_cluster = sorted(n_set - o_set)
            if only_in_file:
                print(f"    Extra labels vs nearest cluster: {only_in_file}")
            if only_in_cluster:
                print(f"    Missing vs nearest cluster: {only_in_cluster}")
    else:
        print(f"\nAll {len(clean)} files fall into the top-2 clusters — no outliers.")


if __name__ == "__main__":
    main()
