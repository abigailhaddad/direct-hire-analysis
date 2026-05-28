#!/usr/bin/env python3
"""
Spot-check the direct hire regex against a single month's parquet file.

1. Sample matched rows — eyeball for noise/false positives
2. Sample non-matched rows — scan for DH language we might be missing
"""

import re
import os
import json
import urllib.request
import duckdb
import random

DIRECT_HIRE_RE = r"(?i)direct[\s-]*hir(?:e|ing)\s*(?:authority|appointment)?"
EXCLUDE_RE = r"(?i)Military Treatment Facilities under DHA"

# Candidate phrases that might indicate DH authority we're NOT catching
CANDIDATE_PATTERNS = [
    r"shortage.{0,20}categor",
    r"critical.{0,10}need",
    r"critical.{0,10}shortage",
    r"\bDHA\b",
    r"hiring.{0,20}authority",
    r"OPM.{0,30}authority",
    r"Schedule.{0,5}[AB]\b",
    r"streamlined.{0,20}hir",
    r"non.competitive",
    r"appointing.{0,20}authority",
]
CANDIDATE_RE = re.compile("|".join(f"(?:{p})" for p in CANDIDATE_PATTERNS), re.IGNORECASE)


def load_hf_token():
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        os.path.expanduser("~/Documents/repos/opm/.env"),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if line.strip().startswith("HF_TOKEN="):
                        return line.strip().split("=", 1)[1]
    return os.environ.get("HF_TOKEN")


def get_parquet_url(split="2023_06"):
    api = f"https://datasets-server.huggingface.co/parquet?dataset=loyoladatamining/usajobs"
    req = urllib.request.Request(api, headers={"User-Agent": "direct-hire-check/1.0"})
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    for f in data["parquet_files"]:
        if f["split"] == split:
            return f["url"]
    raise ValueError(f"Split {split} not found")


def truncate(text, n=300):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:n] + "…" if len(text) > n else text


def main():
    split = "2023_06"
    print(f"Loading {split}...\n")

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    token = load_hf_token()
    if token:
        con.execute("CREATE SECRET hf (TYPE HUGGINGFACE, TOKEN ?)", [token])

    url = get_parquet_url(split)
    all_rows = con.execute(
        "SELECT usajobsControlNumber, title, text FROM read_parquet(?)", [url]
    ).fetchall()
    print(f"Total rows in {split}: {len(all_rows):,}\n")

    matched = [r for r in all_rows if re.search(DIRECT_HIRE_RE, r[2] or "", re.IGNORECASE)
               and not re.search(EXCLUDE_RE, r[2] or "", re.IGNORECASE)]
    unmatched = [r for r in all_rows if r not in matched]

    print(f"Matched: {len(matched):,}  ({100*len(matched)/len(all_rows):.1f}%)")
    print(f"Unmatched: {len(unmatched):,}\n")

    # --- 1. Sample matched rows ---
    print("=" * 70)
    print("MATCHED SAMPLE (checking for noise / false positives)")
    print("=" * 70)
    for row in random.sample(matched, min(15, len(matched))):
        cn, title, text = row
        m = re.search(DIRECT_HIRE_RE, text, re.IGNORECASE)
        start = max(0, m.start() - 150)
        end = min(len(text), m.end() + 150)
        ctx = re.sub(r"\s+", " ", text[start:end]).strip()
        print(f"\n  [{cn}] {title}")
        print(f"  ...{ctx}...")

    # --- 2. Sample unmatched rows — hunt for candidate phrases ---
    print("\n" + "=" * 70)
    print("UNMATCHED WITH CANDIDATE PHRASES (checking for false negatives)")
    print("=" * 70)
    interesting = [r for r in unmatched if CANDIDATE_RE.search(r[2] or "")]
    print(f"\n{len(interesting):,} unmatched rows contain candidate phrases\n")
    for row in random.sample(interesting, min(20, len(interesting))):
        cn, title, text = row
        m = CANDIDATE_RE.search(text)
        start = max(0, m.start() - 100)
        end = min(len(text), m.end() + 150)
        ctx = re.sub(r"\s+", " ", text[start:end]).strip()
        print(f"\n  [{cn}] {title}")
        print(f"  ...{ctx}...")

    # --- 3. Summary of candidate phrase counts in unmatched ---
    print("\n" + "=" * 70)
    print("CANDIDATE PHRASE FREQUENCY IN UNMATCHED ROWS")
    print("=" * 70)
    for pat in CANDIDATE_PATTERNS:
        cr = re.compile(pat)
        n = sum(1 for r in unmatched if cr.search(r[2] or ""))
        print(f"  {n:5,}  {pat}")


if __name__ == "__main__":
    main()
