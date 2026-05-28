#!/usr/bin/env python3
"""
Stream the loyoladatamining/usajobs HuggingFace dataset month by month,
find direct hire authority mentions, and write matches to a CSV.

Runs without downloading the full dataset locally (streaming=True).
Output: results/direct_hire_matches.csv
"""

import re
import csv
import os
import sys
from datasets import load_dataset, get_dataset_split_names

PATTERNS = [
    r'direct[\s-]*hire\s*(?:authority|appointment)?',
    r'direct[\s-]*hiring\s*(?:authority|appointment)?',
    r'Direct[\s-]*Hire[\s-]*Authority',
    r'OPM[\s-]*Direct[\s-]*Hire',
]
COMBINED = re.compile('|'.join(f'(?:{p})' for p in PATTERNS), re.IGNORECASE)
MILITARY_DHA = re.compile(r'Military Treatment Facilities under DHA', re.IGNORECASE)


def extract_match(text, control_number, title, split_name):
    """Return one dict per job if a direct hire mention is found, else None."""
    if not text:
        return None
    for match in COMBINED.finditer(text):
        window = text[max(0, match.start() - 200): match.end() + 200]
        if MILITARY_DHA.search(window):
            continue
        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        context = re.sub(r'\s+', ' ', text[start:end]).strip()
        return {
            'usajobsControlNumber': control_number,
            'title': title,
            'split': split_name,
            'matched_phrase': match.group(),
            'context': context,
        }
    return None


def main():
    output_path = os.path.join(os.path.dirname(__file__), '..', 'results', 'direct_hire_matches.csv')
    output_path = os.path.normpath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print("Fetching available splits...")
    all_splits = get_dataset_split_names("loyoladatamining/usajobs", "postings")
    monthly_splits = sorted(s for s in all_splits if re.match(r'^\d{4}_\d{2}$', s))
    print(f"Found {len(monthly_splits)} monthly splits: {monthly_splits[0]} → {monthly_splits[-1]}")

    fieldnames = ['usajobsControlNumber', 'title', 'split', 'matched_phrase', 'context']

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        total_seen = 0
        total_matched = 0

        for split in monthly_splits:
            split_seen = 0
            split_matched = 0
            print(f"  {split} ... ", end='', flush=True)

            ds = load_dataset(
                "loyoladatamining/usajobs",
                "postings",
                split=split,
                streaming=True,
            )

            for record in ds:
                split_seen += 1
                result = extract_match(
                    record['text'],
                    record['usajobsControlNumber'],
                    record['title'],
                    split,
                )
                if result:
                    writer.writerow(result)
                    split_matched += 1

            f.flush()
            total_seen += split_seen
            total_matched += split_matched
            pct = 100 * split_matched / split_seen if split_seen else 0
            print(f"{split_matched:,} / {split_seen:,} ({pct:.1f}%)")

    print(f"\nDone. {total_matched:,} direct hire postings out of {total_seen:,} total ({100*total_matched/total_seen:.1f}%)")
    print(f"Results written to: {output_path}")


if __name__ == '__main__':
    main()
