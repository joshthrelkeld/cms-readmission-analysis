# CMS Medicare 30-Day Readmission Analysis

Patient-level analysis of 30-day hospital readmissions using the CMS Medicare DE-SynPUF (synthetic claims data), Google BigQuery, and Python.

**Current version:** `analysis_revised.py` (November 2026). The original June 2026 script, `analysis.py`, is kept for comparison; see [What changed from version 1](#what-changed-from-version-1).

## Question

Which Medicare inpatients return to the hospital within 30 days of discharge, which patient characteristics are associated with readmission, and do readmission stays cost more?

## Key findings

- **30-day readmission rate: 9.7%** (6,421 of 66,393 index discharges).
- **Chronic condition count shows the strongest association.** Readmission rises with every additional chronic condition, from 1.2% with none to 25.5% with all 11:

  | Chronic conditions | Same-year flags (all index stays) | Prior-year flags (2009-2010 index stays) |
  |---|---|---|
  | 0-2 | 2.3% | 3.6% |
  | 3-5 | 6.1% | 5.7% |
  | 6-8 | 12.6% | 8.9% |
  | 9-11 | 19.8% | 11.6% |

  Part of the same-year gradient is mechanical: the annual flags are derived from claims in the same year, so they can reflect the index stay and the readmission themselves. Using the previous year's flags, the gradient is smaller (about 3x instead of about 9x) but still rises at every step. This is an association, not an adjusted risk estimate.
- **Differences by age and sex are small.** Rates range from 8.8% to 10.2% across age bands (statistically significant and U-shaped, lowest at 65-74) and are 9.5% (female) vs 9.8% (male), which is not significant.
- **Readmission stays do not reliably cost more.** Across all stays, readmission stays were paid $330 more on average (3.5%; $9,862 vs $9,533), with the same median of $7,000 (99% of payments are whole multiples of $1,000). That difference is statistically significant (Welch t-test p = 0.008; Mann-Whitney p = 0.0003). Within the same patients, the evidence does not support a premium: the mean difference is $180 (paired t-test p = 0.25), but the median difference is -$333 and more patients had cheaper readmission stays (2,572) than more expensive ones (2,289) (Wilcoxon p = 0.04, favoring lower readmission payments).
- **No diagnosis group (DRG) stands out.** A chi-square test across the 526 DRGs with at least 50 index stays finds no evidence that readmission rates vary by DRG (p = 0.90).

All findings come from synthetic data. They demonstrate methodology and do not describe real Medicare beneficiaries (see [Limitations](#limitations)).

## Readmission definition

A simplified definition inspired by the CMS measure:

- **Index stay:** every inpatient discharge with a full 30 days of follow-up left in the data (discharged on or before 2010-12-01).
- **Readmission:** the patient's next admission begins **1 to 30 days** after that discharge. Gaps of 0 days or less (290 same-day admissions and 1,805 overlapping claims) are not counted.
- **Rate:** index stays followed by a readmission, divided by all index stays.
- **Rates by DRG** use the DRG of the index stay, the condition the patient was discharged with.

**Differences from the CMS Hospital-Wide Readmission measure.** Unlike CMS, this analysis:
- includes patients under 65 (11,538 index stays, 17%)
- does not combine transfer chains into a single stay
- applies no exclusions for enrollment gaps, deaths, planned readmissions, or the conditions CMS excludes
- groups by DRG rather than CMS specialty cohorts
- is not risk adjusted

Because only the next stay is checked, 337 readmissions that follow an overlapping stay are not counted.

## What changed from version 1

The June 2026 version reported a 29.6% readmission rate and three DRGs above 40%. An audit found several problems:

| Issue in version 1 | Effect | Fix in version 2 |
|---|---|---|
| Denominator included only stays that followed an earlier stay, not every discharge | Inflated the rate | Rate measured per index discharge, looking forward with `LEAD` |
| Gaps of 0 days or less counted as readmissions | 2,165 of 8,588 flagged readmissions (25%) in the June run were same-day or overlapping claims | Only gaps of 1 to 30 days count |
| DRG rates grouped by the readmission stay's DRG | Misattributed readmissions to conditions | Grouped by the index stay's DRG |
| Ties in admission date sorted unpredictably | Small run-to-run differences (8,585 vs 8,588 readmissions) | Ordered by admission date, discharge date, then claim ID |
| 68 claims stored as two `SEGMENT` rows | Duplicate stays | Segment 1 only (66,705 unique claims) |
| Payment test ignored repeated stays per patient and coarsened, skewed payments | Overstated certainty about a payment premium | Welch t-test, Mann-Whitney, log-scale test, and a within-patient comparison |
| Chronic condition count summed 10 of 11 flags | Alzheimer's flag omitted | All 11 flags summed |

Version 2 also limits index stays to discharges with 30 days of follow-up. This changes the rate by under 0.1 points.

The script prints the version 1 method (rebuilt on the deduplicated data) next to the revised one so the two can be compared directly.

## The 2008-2010 trend

Readmission rates fall sharply by year under both methods (revised: 14.5% in 2008, 7.4% in 2009, 4.2% in 2010). The cause is not fully explained, but the pattern tracks a drop in hospital stays per patient in the synthetic file:

| Year | Beneficiaries | Inpatient claims | Claims per patient with a claim |
|---|---|---|---|
| 2008 | 116,352 | 27,678 | 1.75 |
| 2009 | 114,538 | 25,231 | 1.34 |
| 2010 | 112,754 | 13,572 | 1.16 |

Claims fall by half while the beneficiary population falls 3%, so each patient has fewer stays and fewer chances to be readmitted. CMS notes that 2010 claim counts are lower because of attrition from death and some effects of disclosure treatment. The trend should not be read as real-world improvement. The pooled 9.7% rate is weighted toward 2008 and does not remove this artifact.

## Data

**Source:** CMS 2008-2010 Data Entrepreneurs' Synthetic Public Use File (DE-SynPUF), Sample 1

| BigQuery table | Source file | Rows |
|---|---|---|
| `inpatient_claims` | `DE1_0_2008_to_2010_Inpatient_Claims_Sample_1.csv` | 66,773 (66,705 unique claims; 37,780 patients) |
| `beneficiary_2008` | `DE1_0_2008_Beneficiary_Summary_File_Sample_1.csv` | 116,352 |
| `beneficiary_2009` | `DE1_0_2009_Beneficiary_Summary_File_Sample_1.csv` | 114,538 |
| `beneficiary_2010` | `DE1_0_2010_Beneficiary_Summary_File_Sample_1.csv` | 112,754 |

Each claim is joined to the beneficiary file for its admission year on `DESYNPUF_ID`. 66,169 of 66,393 index stays (99.7%) have a match. All 224 unmatched stays are 2007 admissions, which have no beneficiary file.

**Patient features from the beneficiary files:**
- **Age at admission:** days between birth date and admission date, divided by 365.25
- **Sex:** `BENE_SEX_IDENT_CD` (1 = male, 2 = female)
- **Chronic condition count (0-11):** sum of `SP_ALZHDMTA`, `SP_CHF`, `SP_CHRNKIDN`, `SP_CNCR`, `SP_COPD`, `SP_DEPRESSN`, `SP_DIABETES`, `SP_ISCHMCHT`, `SP_OSTEOPRS`, `SP_RA_OA`, `SP_STRKETIA` (raw coding: 1 = present, 2 = absent), from both the admission-year file and the previous year's file

**Data quality checks printed by the script:** row count vs unique claim IDs, rows missing dates, same-day and overlapping stays excluded, beneficiary match rate, claim volume by year, claims with zero or negative payment (2,213: 2,158 zero and 55 negative, kept in the means and excluded from the log-scale test), and the share of payments that are whole multiples of $1,000.

## Methods

**SQL (BigQuery)**
- Dates stored as integers (`YYYYMMDD`) converted with `PARSE_DATE`
- `LEAD` and `LAG` window functions, partitioned by patient, to find each stay's next admission and previous discharge
- `UNION ALL` of the three beneficiary files, tagged by year, then `LEFT JOIN` on patient ID and year (admission year, and separately the previous year) so unmatched claims are kept rather than dropped
- Chronic condition flags converted from 1/2 coding to 0/1 before summing

**Python**
- `google-cloud-bigquery` to run the queries and load results into pandas
- Readmission rates by year, index-stay DRG (minimum 50 stays), age band, chronic condition count (same-year and prior-year flags), and sex
- `scipy.stats`: Welch t-test, Mann-Whitney U, Welch t-test on log payments, paired t-test and Wilcoxon signed-rank test within patients
- `matplotlib` 2x3 figure saved to `readmission_analysis.png`

## Limitations

- **Synthetic data.** CMS states the DE-SynPUF has very limited inferential research utility and that correlations among variables cannot be relied upon. The 9.7% rate is about half the 19.6% reported for 2003-2004 fee-for-service Medicare (Jencks et al., NEJM 2009). Synthetic processing and this simplified definition likely both contribute.
- **Unadjusted associations.** Rates by chronic condition count, age, and sex are not adjusted for each other or for diagnosis. A logistic regression would be the next step.
- **Simplified definition.** See the differences from the CMS measure above.
- **Repeated stays.** 15,056 patients contribute more than one index stay, and rate comparisons are reported without confidence intervals. Claim-level payment tests treat related stays as independent; the within-patient comparison partly addresses this.

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
