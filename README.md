# Direct Hire Authority Analysis

Identifies federal job postings that mention Direct Hire Authority, using the
[loyoladatamining/usajobs](https://huggingface.co/datasets/loyoladatamining/usajobs)
HuggingFace dataset (~3M postings, 2017–2026).

## Usage

```bash
pip install -r requirements.txt

# Stream dataset from HuggingFace and write matches (~110 monthly splits)
python scripts/find_direct_hire.py

# Render the Quarto report
cd analysis && quarto render direct_hire_analysis.qmd
```

The script queries parquet files directly over HTTP via DuckDB — no local
download. Only matching rows are transferred. Results are written
incrementally to `results/direct_hire_matches.csv`.

## Regex patterns

```
direct[\s-]*hire\s*(?:authority|appointment)?
direct[\s-]*hiring\s*(?:authority|appointment)?
Direct[\s-]*Hire[\s-]*Authority
OPM[\s-]*Direct[\s-]*Hire
```

Mentions are not counted when they sit next to Schedule A disability or 30%-disabled-veteran
language (different authorities), or inside the probationary-period boilerplate "...from a
competitive examination register of eligibles (an announcement opened to the public) or under a
direct hire authority", which appears in postings that are not direct hire. A posting counts if any
one mention survives.

Fixed 2026-11-12: the boilerplate wasn't excluded before, and every posting mentioning "Military
Treatment Facilities under DHA" (Defense Health Agency clinics) was dropped, although those
postings are often direct hire. Results from before the fix are in
`results/direct_hire_matches_before_2026-11-12.csv`.
