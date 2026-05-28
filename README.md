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

False positive excluded: "Military Treatment Facilities under DHA" (Defense Health Agency).
