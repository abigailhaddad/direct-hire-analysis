#!/usr/bin/env python3
"""
Query HuggingFace parquet files directly via DuckDB — no local download.
Fetches the list of parquet URLs from the HF datasets-server API, then
runs a regex filter on each file over HTTP, writing matches to a CSV.

Output: results/direct_hire_matches.csv
"""

import csv
import os
import re
import sys
import urllib.request
import json
import duckdb

HF_PARQUET_API = "https://datasets-server.huggingface.co/parquet?dataset=loyoladatamining/usajobs"

DIRECT_HIRE_RE = r"(?i)direct[\s-]*hir(?:e|ing)\s*(?:authority|appointment)?"
EXCLUDE_RE = r"(?i)Military Treatment Facilities under DHA"

QUERY = """
SELECT
    usajobsControlNumber,
    title,
    regexp_extract(text, '(?i)direct[\\s-]*hir(?:e|ing)(?:\\s*(?:authority|appointment))?') AS matched_phrase,
    regexp_extract(
        text,
        '.{0,100}direct[\\s-]*hir(?:e|ing)(?:\\s*(?:authority|appointment))?.{0,100}'
    ) AS context
FROM read_parquet(?)
WHERE regexp_matches(text, ?)
  AND NOT regexp_matches(text, ?)
"""


def get_parquet_files():
    req = urllib.request.Request(HF_PARQUET_API, headers={"User-Agent": "direct-hire-analysis/1.0"})
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    files = data.get("parquet_files", [])
    # group by split, keep only monthly splits
    by_split = {}
    for f in files:
        split = f["split"]
        if re.match(r"^\d{4}_\d{2}$", split):
            by_split.setdefault(split, []).append(f["url"])
    return dict(sorted(by_split.items()))


def main():
    output_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "results", "direct_hire_matches.csv")
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print("Fetching parquet file list from HuggingFace...")
    splits = get_parquet_files()
    print(f"Found {len(splits)} monthly splits across {sum(len(v) for v in splits.values())} parquet files")

    con = duckdb.connect()

    fieldnames = ["usajobsControlNumber", "title", "split", "matched_phrase", "context"]
    total_seen = 0
    total_matched = 0

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for split, urls in splits.items():
            split_matched = 0
            for url in urls:
                rows = con.execute(QUERY, [url, DIRECT_HIRE_RE, EXCLUDE_RE]).fetchall()
                for row in rows:
                    writer.writerow({
                        "usajobsControlNumber": row[0],
                        "title": row[1],
                        "split": split,
                        "matched_phrase": row[2],
                        "context": re.sub(r"\s+", " ", row[3]).strip() if row[3] else "",
                    })
                    split_matched += 1
            f.flush()
            total_matched += split_matched
            print(f"  {split}: {split_matched:,} matches", flush=True)

    print(f"\nDone. {total_matched:,} direct hire postings written to {output_path}")


if __name__ == "__main__":
    main()
