# CMS Medicare 30-Day Readmission Analysis

Patient-level longitudinal analysis of 30-day hospital readmission patterns using CMS Medicare SynPUF (Synthetic Public Use File) data, Google BigQuery, and Python.

## Overview

This project analyzes inpatient claims data for 37,780 Medicare beneficiaries to identify readmission patterns, quantify cost differences, and surface high-risk diagnosis codes. The core question: which patients are readmitted within 30 days of discharge, and what does that cost Medicare?

## Key Findings

- **29.61% 30-day readmission rate** across 28,993 analyzed claims
- Readmitted patients cost Medicare **$492 per claim * on average ($10,093 vs $9,601)
- Payment difference is statistically significant (t-test, p < 0.0001)
- DRG codes 289, 293, and 853 show the highest readmission rates (42–44%)
- Readmission rate declined from 44% in 2008 to 15% in 2010

## Data

**Source:** CMS DE-SynPUF (Data Entrepreneurs' Synthetic Public Use File), Sample 1  
**Tables used:**
- `inpatient_claims` — 66,773 inpatient claims across 37,780 unique patients
- `beneficiary_2008/2009/2010` — annual beneficiary demographics and chronic conditions

**Note:** SynPUF is synthetic data designed to mirror the structure of real Medicare claims. Findings demonstrate methodology and should not be interpreted as reflecting actual Medicare readmission rates.

## Methods

**SQL (BigQuery)**
- Window functions (`LAG`, `PARTITION BY`) to identify sequential admissions per patient
- `DATE_DIFF` with `PARSE_DATE` to calculate days between discharge and next admission
- Aggregations by year and DRG code to surface temporal and diagnostic patterns

**Python**
- `google-cloud-bigquery` client to pull query results into pandas DataFrames
- `scipy.stats.ttest_ind` to test payment difference significance between readmitted and non-readmitted cohorts
- `matplotlib` for visualization

## Repository Structure
cms-readmission-analysis/

├── analysis.py        # Core analysis script

└── README.md

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