#!/usr/bin/env python3
"""
Count job postings mentioning Python, Stata (and a few others for context)
per month across the HuggingFace usajobs dataset.

Single DuckDB query per parquet file — no local download.
Output: results/tool_counts.csv
"""

import csv
import os
import re
import urllib.request
import json
import duckdb

HF_PARQUET_API = "https://datasets-server.huggingface.co/parquet?dataset=loyoladatamining/usajobs"

# Each tool: (match_pattern, exclude_pattern_or_None)
# Python: exclude snake/wildlife/firearms contexts
PYTHON_EXCLUDE = r"(?i)\b(?:burmese|ball\s+python|rock\s+python|reticulated|constrictor|python\s+snake|invasive\s+snake|colt\s+python|python\s+revolver)\b"
# R: \bR\b alone is too noisy; require "R programming" or "in R" or "R and Python" etc.
R_MATCH = r"(?i)(?:\bR\s+programming\b|\bprogramming\s+in\s+R\b|\busing\s+R\b|\bR\s+and\s+Python\b|\bPython\s+and\s+R\b|\bR[,/]\s*Python\b|\bR\s+or\s+Python\b)"

TOOLS = {
    "python":  (r"(?i)\bpython\b",   PYTHON_EXCLUDE),
    "stata":   (r"(?i)\bstata\b",    None),
    "r":       (R_MATCH,             None),
    "sas":     (r"(?i)\bSAS\b",      None),
    "sql":     (r"(?i)\bSQL\b",      None),
    "excel":   (r"(?i)\bexcel\b",    None),
    "tableau": (r"(?i)\btableau\b",  None),
    "spss":    (r"(?i)\bSPSS\b",     None),
}


def build_query(tools):
    filters = []
    for name, (match_pat, excl_pat) in tools.items():
        cond = f"regexp_matches(text, '{match_pat}')"
        if excl_pat:
            cond += f" AND NOT regexp_matches(text, '{excl_pat}')"
        filters.append(f"COUNT(*) FILTER (WHERE {cond}) AS {name}_count")
    counts = ",\n    ".join(filters)
    return f"""
SELECT
    COUNT(*) AS total,
    {counts}
FROM read_parquet(?)
"""


def load_hf_token():
    if os.environ.get("HF_TOKEN"):
        return os.environ["HF_TOKEN"]
    for path in [
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        os.path.expanduser("~/Documents/repos/opm/.env"),
    ]:
        path = os.path.normpath(path)
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if line.strip().startswith("HF_TOKEN="):
                        return line.strip().split("=", 1)[1]
    return None


def get_parquet_files():
    req = urllib.request.Request(HF_PARQUET_API, headers={"User-Agent": "tool-counts/1.0"})
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    by_split = {}
    for f in data.get("parquet_files", []):
        split = f["split"]
        if re.match(r"^\d{4}_\d{2}$", split):
            by_split.setdefault(split, []).append(f["url"])
    return dict(sorted(by_split.items()))


def main():
    output_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "results", "tool_counts.csv")
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print("Fetching parquet file list...")
    splits = get_parquet_files()
    print(f"Found {len(splits)} monthly splits")

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    token = load_hf_token()
    if token:
        con.execute("CREATE SECRET hf (TYPE HUGGINGFACE, TOKEN ?)", [token])
        print("HuggingFace token loaded.")

    query = build_query(TOOLS)
    tool_names = list(TOOLS.keys())
    fieldnames = ["split"] + [f"{t}_count" for t in tool_names] + ["total_postings"]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for split, urls in splits.items():
            row = {"split": split, "total_postings": 0}
            for t in tool_names:
                row[f"{t}_count"] = 0

            for url in urls:
                result = con.execute(query, [url]).fetchone()
                row["total_postings"] += result[0]
                for i, t in enumerate(tool_names):
                    row[f"{t}_count"] += result[i + 1]

            f.flush()
            writer.writerow(row)
            print(f"  {split}: python={row['python_count']:,}  stata={row['stata_count']:,}  "
                  f"r={row['r_count']:,}  sas={row['sas_count']:,}  total={row['total_postings']:,}", flush=True)

    print(f"\nDone. Results written to {output_path}")


if __name__ == "__main__":
    main()
