# CMS Medicare 30-Day Readmission Analysis

Patient-level analysis of 30-day hospital readmissions using the CMS Medicare DE-SynPUF (synthetic claims data), Google BigQuery, and Python.

**Current version:** `analysis_revised.py` (November 2026). The original June 2026 script, `analysis.py`, is kept for comparison; see [What changed from version 1](#what-changed-from-version-1).

## Question

Which Medicare inpatients return to the hospital within 30 days of discharge, which patient characteristics go with higher readmission, and do readmission stays cost more?

## Key findings

- **30-day readmission rate: 9.7%** (6,421 of 66,393 index discharges).
- **Chronic disease burden is the strongest pattern.** Readmission rises with every additional chronic condition, from 1.2% with none to 25.5% with all 11:

  | Chronic conditions | Index stays | Readmission rate |
  |---|---|---|
  | 0-2 | 7,274 | 2.3% |
  | 3-5 | 24,607 | 6.1% |
  | 6-8 | 28,534 | 12.6% |
  | 9-11 | 5,754 | 19.8% |

- **Age and sex barely matter.** Rates range from 8.8% to 10.2% across age bands, and 9.5% (female) vs 9.8% (male).
- **Readmission stays cost slightly more, mostly because of who is readmitted.** Readmission stays were paid $330 more on average (3.5%; $9,862 vs $9,533), with identical medians of $7,000. The difference is significant across stays (Welch t-test p = 0.008; Mann-Whitney p = 0.0003). Comparing readmission stays with the same patients' other stays, the difference falls to $180 (paired t-test p = 0.25; Wilcoxon p = 0.04), which suggests most of the premium reflects sicker patients rather than the readmission stay itself.
- **No diagnosis group (DRG) stands out reliably.** The highest-rate DRGs each have only 50 to 80 index stays among 526 DRGs with at least 50 stays (median rate 9.6%), so their rankings are consistent with chance.

All findings come from synthetic data. They demonstrate methodology and do not describe real Medicare beneficiaries (see [Limitations](#limitations)).

## Readmission definition

A simplified version of the CMS approach:

- **Index stay:** every inpatient discharge with a full 30 days of follow-up left in the data (discharged on or before 2010-12-01).
- **Readmission:** the patient's next admission begins **1 to 30 days** after that discharge. Gaps of 0 days or less (same-day transfers and overlapping claims) are not counted.
- **Rate:** index stays followed by a readmission, divided by all index stays.
- **Rates by DRG** use the DRG of the index stay, the condition the patient was discharged with.

Not replicated from CMS: exclusions for planned readmissions, deaths, and gaps in Medicare enrollment.

## What changed from version 1

The June 2026 version reported a 29.6% readmission rate and three DRGs above 40%. An audit found several problems:

| Issue in version 1 | Effect | Fix in version 2 |
|---|---|---|
| Denominator included only stays that followed an earlier stay, not every discharge | Inflated the rate | Rate measured per index discharge, looking forward with `LEAD` |
| Gaps of 0 days or less counted as readmissions | 2,097 of 8,518 flagged readmissions (25%) were same-day or overlapping claims | Only gaps of 1 to 30 days count |
| Discharges in the last 30 days of data had no follow-up window | Undercounted readmissions at the end of the data | Index stays limited to discharges on or before 2010-12-01 |
| DRG rates grouped by the readmission stay's DRG | Misattributed readmissions to conditions | Grouped by the index stay's DRG |
| Ties in admission date sorted unpredictably | Small run-to-run differences | Ordered by admission date, discharge date, then claim ID |
| 68 claims stored as two `SEGMENT` rows | Duplicate stays | Segment 1 only (66,705 unique claims) |
| Student's t-test on heavily skewed payments | Inappropriate test | Welch t-test, Mann-Whitney, log-scale test, and a within-patient comparison |
| Chronic condition count summed 10 of 11 flags | Alzheimer's flag omitted | All 11 flags summed |

The script prints the version 1 method next to the revised one so the two can be compared directly.

## The 2008-2010 trend

Readmission rates fall sharply by year under both methods (revised: 14.5% in 2008, 7.4% in 2009, 4.2% in 2010). This trend reflects how the synthetic file was built, not real-world improvement:

| Year | Beneficiaries | Inpatient claims |
|---|---|---|
| 2008 | 116,352 | 27,678 |
| 2010 | 112,754 | 13,572 |
| Change | -3% | -51% |

Claims fall by half while the beneficiary population barely changes, so each patient has fewer stays and fewer chances to be readmitted. CMS notes that 2010 claim counts are lower because of attrition from death and the disclosure processing used to create the file. The findings above therefore use the pooled 2008-2010 rate.

## Data

**Source:** CMS 2008-2010 Data Entrepreneurs' Synthetic Public Use File (DE-SynPUF), Sample 1

| BigQuery table | Source file | Rows |
|---|---|---|
| `inpatient_claims` | `DE1_0_2008_to_2010_Inpatient_Claims_Sample_1.csv` | 66,773 (66,705 unique claims; 37,780 patients) |
| `beneficiary_2008` | `DE1_0_2008_Beneficiary_Summary_File_Sample_1.csv` | 116,352 |
| `beneficiary_2009` | `DE1_0_2009_Beneficiary_Summary_File_Sample_1.csv` | 114,538 |
| `beneficiary_2010` | `DE1_0_2010_Beneficiary_Summary_File_Sample_1.csv` | 112,754 |

Each claim is joined to the beneficiary file for its admission year on `DESYNPUF_ID`. 66,169 of 66,393 index stays (99.7%) have a match. The unmatched stays are mostly 2007 admissions, which have no beneficiary file.

**Patient features from the beneficiary files:**
- **Age at admission:** days between birth date and admission date, divided by 365.25
- **Sex:** `BENE_SEX_IDENT_CD` (1 = male, 2 = female)
- **Chronic condition count (0-11):** sum of `SP_ALZHDMTA`, `SP_CHF`, `SP_CHRNKIDN`, `SP_CNCR`, `SP_COPD`, `SP_DEPRESSN`, `SP_DIABETES`, `SP_ISCHMCHT`, `SP_OSTEOPRS`, `SP_RA_OA`, `SP_STRKETIA` (raw coding: 1 = present, 2 = absent)

**Data quality checks printed by the script:** row count vs unique claim IDs, rows missing dates, same-day and overlapping stays excluded, beneficiary match rate, claim volume by year, and claims with zero or negative payment (2,213, kept in the means and excluded from the log-scale test).

## Methods

**SQL (BigQuery)**
- Dates stored as integers (`YYYYMMDD`) converted with `PARSE_DATE`
- `LEAD` and `LAG` window functions, partitioned by patient, to find each stay's next admission and previous discharge
- `UNION ALL` of the three beneficiary files, tagged by year, then `LEFT JOIN` on patient ID and admission year so unmatched claims are kept rather than dropped
- Chronic condition flags converted from 1/2 coding to 0/1 before summing

**Python**
- `google-cloud-bigquery` to run the queries and load results into pandas
- Readmission rates by year, index-stay DRG (minimum 50 stays), age band, chronic condition count, and sex
- `scipy.stats`: Welch t-test, Mann-Whitney U, Welch t-test on log payments, paired t-test and Wilcoxon signed-rank test within patients
- `matplotlib` 2x3 figure saved to `readmission_analysis.png`

## Limitations

- **Synthetic data.** CMS states the DE-SynPUF has very limited value for drawing conclusions about Medicare beneficiaries. The 9.7% rate is well below the roughly 20% real-world Medicare benchmark, consistent with synthetic processing that breaks up patient histories.
- **Unadjusted comparisons.** The chronic condition gradient has not been adjusted for age, diagnosis, or other factors. A logistic regression would be the next step.
- **Simplified CMS definition.** Planned readmissions, deaths, and enrollment gaps are not excluded.
- **Claim-level payment comparison.** Patients contribute multiple stays, so claim-level tests treat related observations as independent. The within-patient comparison partly addresses this.

This is a descriptive analysis, not a predictive model.

## Repository structure

```
cms-readmission-analysis/
├── analysis_revised.py   # Current analysis (November 2026)
├── analysis.py           # Original version (June 2026), kept for comparison
├── requirements.txt
└── README.md
```

## Setup

**Prerequisites:** Python 3.12+, Google Cloud SDK, a BigQuery project with the four tables above in a dataset named `cms_synpuf`

```bash
git clone https://github.com/joshthrelkeld/cms-readmission-analysis.git
cd cms-readmission-analysis

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

gcloud auth application-default login
gcloud auth application-default set-quota-project cms-readmission-analysis

python analysis_revised.py
```

## Skills demonstrated

Google BigQuery · SQL window functions (`LEAD`, `LAG`) · Claims data quality auditing · Patient-level longitudinal analysis · Python (pandas, scipy, matplotlib) · Nonparametric and paired hypothesis testing · Medicare claims data
