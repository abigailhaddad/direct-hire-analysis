#!/usr/bin/env python3
"""
Query HuggingFace parquet files directly via DuckDB — no local download.

Two-stage filtering:
  1. DuckDB: fast pre-filter — any "direct hire" mention, whole-doc MTF/DHA exclusion
  2. Python: per-match context check — exclude Schedule A disability and
     30%+ disabled vet hiring authority mentions (different authorities, not DHA)

Looks for HF_TOKEN in .env files (checks repo root and ~/Documents/repos/opm/.env).

Output:
  results/direct_hire_matches.csv  — one row per matched posting
  results/split_totals.csv         — total postings per month (for rate calculations)
"""

import csv
import os
import re
import urllib.request
import json
import duckdb

HF_PARQUET_API = "https://datasets-server.huggingface.co/parquet?dataset=loyoladatamining/usajobs"

# Stage 1: DuckDB pre-filter (whole-document)
CANDIDATE_QUERY = r"""
SELECT usajobsControlNumber, title, text
FROM read_parquet(?)
WHERE regexp_matches(text, '(?i)direct[\s-]*hir(?:e|ing)')
  AND NOT regexp_matches(text, '(?i)Military Treatment Facilities under DHA')
"""
COUNT_QUERY = "SELECT COUNT(*) FROM read_parquet(?)"

# Stage 2: Python per-match context filtering
DIRECT_HIRE_RE = re.compile(r"direct[\s-]*hir(?:e|ing)\s*(?:authority|appointment)?", re.IGNORECASE)

# Per-exclusion: (compiled pattern, chars_before_match, chars_after_match)
# Tight asymmetric windows so boilerplate in distant sections of the same posting won't misfire.
CONTEXT_EXCLUDES = [
    # Schedule A disability appt — FP phrase is "direct hire ... Schedule A" (~35 chars after)
    (re.compile(r"Schedule\s*A", re.IGNORECASE), 20, 100),
    # 30% disabled vet authority — appears within ~60 chars, either side
    (re.compile(r"(?:disabled\s+vet.{0,50}30\s*%|30\s*%\+?.{0,50}disabled\s+vet)", re.IGNORECASE), 80, 80),
]


def load_hf_token():
    if os.environ.get("HF_TOKEN"):
        return os.environ["HF_TOKEN"]
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
    return None


def get_parquet_files():
    req = urllib.request.Request(HF_PARQUET_API, headers={"User-Agent": "direct-hire-analysis/1.0"})
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    by_split = {}
    for f in data.get("parquet_files", []):
        split = f["split"]
        if re.match(r"^\d{4}_\d{2}$", split):
            by_split.setdefault(split, []).append(f["url"])
    return dict(sorted(by_split.items()))


def find_genuine_match(text, control_number, title, split):
    """
    Iterate over all direct-hire matches in text.
    Return the first one that passes all context exclusion checks.
    Each exclusion uses its own (before, after) window so distant boilerplate doesn't fire.
    Returns None if every match is a false positive.
    """
    for match in DIRECT_HIRE_RE.finditer(text):
        fp = False
        for pat, before, after in CONTEXT_EXCLUDES:
            ctx = text[max(0, match.start() - before): min(len(text), match.end() + after)]
            if pat.search(ctx):
                fp = True
                break
        if fp:
            continue
        ctx_clean = re.sub(r"\s+", " ", ctx).strip()
        return {
            "usajobsControlNumber": control_number,
            "title": title,
            "split": split,
            "matched_phrase": match.group(),
            "context": ctx_clean,
        }
    return None


def main():
    base = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    matches_path = os.path.join(base, "results", "direct_hire_matches.csv")
    totals_path = os.path.join(base, "results", "split_totals.csv")
    os.makedirs(os.path.join(base, "results"), exist_ok=True)

    print("Fetching parquet file list from HuggingFace...")
    splits = get_parquet_files()
    print(f"Found {len(splits)} monthly splits across {sum(len(v) for v in splits.values())} parquet files")

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    token = load_hf_token()
    if token:
        con.execute("CREATE SECRET hf (TYPE HUGGINGFACE, TOKEN ?)", [token])
        print("HuggingFace token loaded.")
    else:
        print("No HF_TOKEN found — proceeding unauthenticated (may hit rate limits).")

    match_fields = ["usajobsControlNumber", "title", "split", "matched_phrase", "context"]
    total_fields = ["split", "total_postings", "dh_candidates", "dh_matched"]

    total_matched = 0

    with open(matches_path, "w", newline="", encoding="utf-8") as mf, \
         open(totals_path, "w", newline="", encoding="utf-8") as tf:

        mwriter = csv.DictWriter(mf, fieldnames=match_fields)
        mwriter.writeheader()
        twriter = csv.DictWriter(tf, fieldnames=total_fields)
        twriter.writeheader()

        for split, urls in splits.items():
            split_total = 0
            split_candidates = 0
            split_matched = 0

            for url in urls:
                split_total += con.execute(COUNT_QUERY, [url]).fetchone()[0]
                candidates = con.execute(CANDIDATE_QUERY, [url]).fetchall()
                split_candidates += len(candidates)

                for cn, title, text in candidates:
                    result = find_genuine_match(text or "", cn, title, split)
                    if result:
                        mwriter.writerow(result)
                        split_matched += 1

            mf.flush()
            twriter.writerow({
                "split": split,
                "total_postings": split_total,
                "dh_candidates": split_candidates,
                "dh_matched": split_matched,
            })
            tf.flush()
            total_matched += split_matched
            pct = 100 * split_matched / split_total if split_total else 0
            filtered = split_candidates - split_matched
            print(f"  {split}: {split_matched:,} matched ({pct:.1f}%), {filtered:,} filtered out", flush=True)

    print(f"\nDone. {total_matched:,} genuine direct hire postings written to {matches_path}")


if __name__ == "__main__":
    main()
