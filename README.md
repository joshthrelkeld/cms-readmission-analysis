# CMS Medicare 30-Day Readmission Analysis

Patient-level longitudinal analysis of 30-day hospital readmission patterns using CMS Medicare SynPUF (Synthetic Public Use File) data, Google BigQuery, and Python.

## Overview

This project analyzes inpatient claims data for 37,780 Medicare beneficiaries to identify readmission patterns, quantify cost differences, and surface high-risk diagnosis codes. Each claim is enriched with patient-level demographics and chronic condition data from the annual beneficiary files. The core question: which patients are readmitted within 30 days of discharge, and what does that cost Medicare?

## Key Findings

- **29.61% 30-day readmission rate** across 28,993 analyzed claims
- Readmitted patients cost Medicare **$492 more per claim** on average ($10,093 vs $9,601)
- Payment difference is statistically significant (t-test, p < 0.0001)
- DRG codes 289, 293, and 853 show the highest readmission rates (42–44%)
- Readmission rate appears to decline from ~44% in 2008 to ~15% in 2010 — this is a SynPUF data artifact (see note below) and does not reflect a real clinical trend

## Data

**Source:** CMS DE-SynPUF (Data Entrepreneurs' Synthetic Public Use File), Sample 1  
**Tables used:**
- `inpatient_claims` — 66,773 inpatient claims across 37,780 unique patients
- `beneficiary_2008`, `beneficiary_2009`, `beneficiary_2010` — annual beneficiary snapshots joined to claims on `DESYNPUF_ID`, matched by claim year, providing demographics and chronic condition flags

**Patient-level features derived from the beneficiary join:**
- **Age at admission** — computed via `DATE_DIFF` between `CLM_ADMSN_DT` and `BENE_BIRTH_DT`
- **Sex** — from `BENE_SEX_IDENT_CD` (1 = Male, 2 = Female)
- **Chronic condition count** — sum of 11 binary flags (`SP_ALZHDMTA`, `SP_CHF`, `SP_CHRNKIDN`, `SP_CNCR`, `SP_COPD`, `SP_DEPRESSN`, `SP_DIABETES`, `SP_ISCHMCHT`, `SP_OSTEOPRS`, `SP_RA_OA`, `SP_STRKETIA`), where 1 = condition present and 2 = absent in the raw data

**Note on the 2008–2010 readmission trend:** The apparent decline from ~44% to ~15% across years is an artifact of how SynPUF was constructed — claim volume and patient coverage vary significantly by year in the synthetic dataset. This pattern should not be interpreted as evidence of improving readmission rates in real Medicare data.

**Note on SynPUF generally:** SynPUF is synthetic data designed to mirror the structure of real Medicare claims. All findings demonstrate methodology only and do not reflect actual Medicare readmission rates or clinical outcomes.

## Methods

**SQL (BigQuery)**
- `UNION ALL` across three beneficiary year tables, tagged with `bene_year`, then `LEFT JOIN`ed to claims on `(DESYNPUF_ID, claim_year)` to match each claim to the correct annual beneficiary snapshot
- Window functions (`LAG`, `PARTITION BY`) to identify sequential admissions per patient
- `DATE_DIFF` with `PARSE_DATE` to calculate days between discharge and next admission, and age at admission
- Chronic condition flags converted from 1/2 encoding to 0/1 inline via `CASE` expressions before summing
- Aggregations by year, DRG code, age band, chronic condition count, and sex

**Python**
- `google-cloud-bigquery` client to pull query results into pandas DataFrames
- `scipy.stats.ttest_ind` to test payment difference significance between readmitted and non-readmitted cohorts
- `pd.cut` with left-inclusive age bands (Under 65, 65–74, 75–84, 85+)
- `matplotlib` 2×3 panel figure: readmission rate by year, payment distribution, top DRG codes, readmission rate by age band, by chronic condition count, and by sex

## Repository Structure
```
cms-readmission-analysis/
├── analysis.py        # Core analysis script
└── README.md
```

## Setup

**Prerequisites:** Python 3.12+, Google Cloud SDK, BigQuery access

```bash
# Clone the repo
git clone https://github.com/joshthrelkeld/cms-readmission-analysis.git
cd cms-readmission-analysis

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install google-cloud-bigquery pandas scipy matplotlib db-dtypes

# Authenticate with GCP
gcloud auth application-default login
gcloud config set project cms-readmission-analysis

# Run analysis
python analysis.py
```

## Skills Demonstrated

Google BigQuery · SQL window functions · Patient-level longitudinal analysis · Python (pandas, scipy, matplotlib) · Google Cloud Platform · Statistical hypothesis testing · Medicare claims data
