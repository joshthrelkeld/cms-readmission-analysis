from google.cloud import bigquery
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

client = bigquery.Client(project="cms-readmission-analysis")

# ── 1. Core readmission analysis ──────────────────────────────────────────────
print("Running core readmission analysis...")

core_query = """
WITH beneficiary AS (
  -- Union all three years; each patient may appear in multiple years,
  -- so we keep one row per (DESYNPUF_ID, year) for the year-matched join.
  SELECT DESYNPUF_ID, BENE_BIRTH_DT, BENE_SEX_IDENT_CD,
         SP_CHF, SP_CHRNKIDN, SP_CNCR, SP_COPD, SP_DEPRESSN,
         SP_DIABETES, SP_ISCHMCHT, SP_OSTEOPRS, SP_RA_OA, SP_STRKETIA,
         2008 AS bene_year
  FROM `cms-readmission-analysis.cms_synpuf.beneficiary_2008`
  UNION ALL
  SELECT DESYNPUF_ID, BENE_BIRTH_DT, BENE_SEX_IDENT_CD,
         SP_CHF, SP_CHRNKIDN, SP_CNCR, SP_COPD, SP_DEPRESSN,
         SP_DIABETES, SP_ISCHMCHT, SP_OSTEOPRS, SP_RA_OA, SP_STRKETIA,
         2009 AS bene_year
  FROM `cms-readmission-analysis.cms_synpuf.beneficiary_2009`
  UNION ALL
  SELECT DESYNPUF_ID, BENE_BIRTH_DT, BENE_SEX_IDENT_CD,
         SP_CHF, SP_CHRNKIDN, SP_CNCR, SP_COPD, SP_DEPRESSN,
         SP_DIABETES, SP_ISCHMCHT, SP_OSTEOPRS, SP_RA_OA, SP_STRKETIA,
         2010 AS bene_year
  FROM `cms-readmission-analysis.cms_synpuf.beneficiary_2010`
),
ordered_claims AS (
  SELECT
    c.DESYNPUF_ID,
    c.CLM_ADMSN_DT,
    c.NCH_BENE_DSCHRG_DT,
    c.CLM_PMT_AMT,
    c.CLM_DRG_CD,
    CAST(SUBSTR(CAST(c.CLM_ADMSN_DT AS STRING), 1, 4) AS INT64) AS claim_year,
    LAG(c.NCH_BENE_DSCHRG_DT) OVER (
      PARTITION BY c.DESYNPUF_ID ORDER BY c.CLM_ADMSN_DT
    ) AS prev_discharge_dt
  FROM `cms-readmission-analysis.cms_synpuf.inpatient_claims` c
),
readmissions AS (
  SELECT
    oc.DESYNPUF_ID,
    oc.CLM_ADMSN_DT,
    oc.NCH_BENE_DSCHRG_DT,
    oc.CLM_PMT_AMT,
    oc.CLM_DRG_CD,
    oc.claim_year,
    CASE
      WHEN DATE_DIFF(
        PARSE_DATE('%Y%m%d', CAST(oc.CLM_ADMSN_DT AS STRING)),
        PARSE_DATE('%Y%m%d', CAST(oc.prev_discharge_dt AS STRING)),
        DAY
      ) <= 30 THEN 1
      ELSE 0
    END AS is_readmission
  FROM ordered_claims oc
  WHERE oc.prev_discharge_dt IS NOT NULL
)
SELECT
  r.*,
  b.BENE_BIRTH_DT,
  b.BENE_SEX_IDENT_CD,
  -- Age at admission in years
  DATE_DIFF(
    PARSE_DATE('%Y%m%d', CAST(r.CLM_ADMSN_DT AS STRING)),
    PARSE_DATE('%Y%m%d', CAST(b.BENE_BIRTH_DT AS STRING)),
    YEAR
  ) AS age_at_admission,
  -- Chronic condition flags: 1 = present, 2 = absent; convert to 0/1
  (CASE WHEN b.SP_CHF      = 1 THEN 1 ELSE 0 END +
   CASE WHEN b.SP_CHRNKIDN = 1 THEN 1 ELSE 0 END +
   CASE WHEN b.SP_CNCR     = 1 THEN 1 ELSE 0 END +
   CASE WHEN b.SP_COPD     = 1 THEN 1 ELSE 0 END +
   CASE WHEN b.SP_DEPRESSN = 1 THEN 1 ELSE 0 END +
   CASE WHEN b.SP_DIABETES  = 1 THEN 1 ELSE 0 END +
   CASE WHEN b.SP_ISCHMCHT = 1 THEN 1 ELSE 0 END +
   CASE WHEN b.SP_OSTEOPRS = 1 THEN 1 ELSE 0 END +
   CASE WHEN b.SP_RA_OA    = 1 THEN 1 ELSE 0 END +
   CASE WHEN b.SP_STRKETIA = 1 THEN 1 ELSE 0 END
  ) AS chronic_condition_count
FROM readmissions r
LEFT JOIN beneficiary b
  ON r.DESYNPUF_ID = b.DESYNPUF_ID
  AND r.claim_year = b.bene_year
"""

df = client.query(core_query).to_dataframe()
print(f"Total claims analyzed: {len(df)}")
print(f"Total readmissions: {df['is_readmission'].sum()}")
print(f"Readmission rate: {df['is_readmission'].mean() * 100:.2f}%")

# ── 2. Payment analysis ────────────────────────────────────────────────────────
readmitted = df[df['is_readmission'] == 1]['CLM_PMT_AMT']
not_readmitted = df[df['is_readmission'] == 0]['CLM_PMT_AMT']

print(f"\nAvg payment (readmitted):     ${readmitted.mean():,.2f}")
print(f"Avg payment (not readmitted): ${not_readmitted.mean():,.2f}")

t_stat, p_value = stats.ttest_ind(readmitted, not_readmitted)
print(f"T-test p-value: {p_value:.4f}")
if p_value < 0.05:
    print("Payment difference is statistically significant (p < 0.05)")
else:
    print("Payment difference is NOT statistically significant")

# ── 3. Readmission rate by year ────────────────────────────────────────────────
df['admission_year'] = df['CLM_ADMSN_DT'].astype(str).str[:4]
yearly = df.groupby('admission_year').agg(
    total_claims=('is_readmission', 'count'),
    readmissions=('is_readmission', 'sum')
).reset_index()
yearly['readmission_rate'] = yearly['readmissions'] / yearly['total_claims'] * 100
print("\nReadmission rate by year:")
print(yearly)

# ── 4. Top DRG codes by readmission rate ──────────────────────────────────────
drg = df.groupby('CLM_DRG_CD').agg(
    total=('is_readmission', 'count'),
    readmissions=('is_readmission', 'sum')
).reset_index()
drg['rate'] = drg['readmissions'] / drg['total'] * 100
drg = drg[drg['total'] >= 50].sort_values('rate', ascending=False).head(10)
print("\nTop 10 DRG codes by readmission rate (min 50 claims):")
print(drg)

# ── 5. Patient feature analysis ───────────────────────────────────────────────
df_bene = df.dropna(subset=['age_at_admission', 'chronic_condition_count'])

age_bins = [0, 65, 75, 85, 120]
age_labels = ['Under 65', '65–74', '75–84', '85+']
df_bene['age_band'] = pd.cut(df_bene['age_at_admission'], bins=age_bins, labels=age_labels, right=False)

age_breakdown = df_bene.groupby('age_band', observed=True).agg(
    total_claims=('is_readmission', 'count'),
    readmissions=('is_readmission', 'sum')
).reset_index()
age_breakdown['readmission_rate'] = age_breakdown['readmissions'] / age_breakdown['total_claims'] * 100
print("\nReadmission rate by age band:")
print(age_breakdown)

cc_breakdown = df_bene.groupby('chronic_condition_count').agg(
    total_claims=('is_readmission', 'count'),
    readmissions=('is_readmission', 'sum')
).reset_index()
cc_breakdown['readmission_rate'] = cc_breakdown['readmissions'] / cc_breakdown['total_claims'] * 100
print("\nReadmission rate by chronic condition count:")
print(cc_breakdown)

sex_map = {1: 'Male', 2: 'Female'}
df_bene['sex'] = df_bene['BENE_SEX_IDENT_CD'].map(sex_map)
sex_breakdown = df_bene.groupby('sex').agg(
    total_claims=('is_readmission', 'count'),
    readmissions=('is_readmission', 'sum')
).reset_index()
sex_breakdown['readmission_rate'] = sex_breakdown['readmissions'] / sex_breakdown['total_claims'] * 100
print("\nReadmission rate by sex:")
print(sex_breakdown)

# ── 6. Visualizations ─────────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 3, figsize=(15, 10))
fig.suptitle('CMS SynPUF Medicare Readmission Analysis', fontsize=14, fontweight='bold')
axes = axes.flatten()

# Chart 1: Readmission rate by year
yearly_filtered = yearly[yearly['admission_year'].isin(['2008', '2009', '2010'])]
axes[0].bar(yearly_filtered['admission_year'], yearly_filtered['readmission_rate'], color='steelblue')
axes[0].set_title('30-Day Readmission Rate by Year')
axes[0].set_ylabel('Readmission Rate (%)')
axes[0].set_xlabel('Year')

# Chart 2: Payment distribution
axes[1].boxplot([not_readmitted.clip(0, 50000), readmitted.clip(0, 50000)],
                tick_labels=['Not Readmitted', 'Readmitted'])
axes[1].set_title('Payment Distribution by Readmission Status')
axes[1].set_ylabel('Payment Amount ($)')

# Chart 3: Top DRG codes
axes[2].barh(drg['CLM_DRG_CD'].astype(str), drg['rate'], color='coral')
axes[2].set_title('Top 10 DRG Codes by Readmission Rate')
axes[2].set_xlabel('Readmission Rate (%)')
axes[2].set_ylabel('DRG Code')

# Chart 4: Readmission rate by age band
axes[3].bar(age_breakdown['age_band'].astype(str), age_breakdown['readmission_rate'], color='mediumpurple')
axes[3].set_title('30-Day Readmission Rate by Age Band')
axes[3].set_ylabel('Readmission Rate (%)')
axes[3].set_xlabel('Age Band')

# Chart 5: Readmission rate by chronic condition count
axes[4].bar(cc_breakdown['chronic_condition_count'].astype(str), cc_breakdown['readmission_rate'], color='teal')
axes[4].set_title('Readmission Rate by Chronic Condition Count')
axes[4].set_ylabel('Readmission Rate (%)')
axes[4].set_xlabel('Number of Chronic Conditions')

# Chart 6: Readmission rate by sex
axes[5].bar(sex_breakdown['sex'], sex_breakdown['readmission_rate'], color='goldenrod')
axes[5].set_title('Readmission Rate by Sex')
axes[5].set_ylabel('Readmission Rate (%)')
axes[5].set_xlabel('Sex')

plt.tight_layout()
plt.savefig('readmission_analysis.png', dpi=150, bbox_inches='tight')
print("\nVisualization saved to readmission_analysis.png")
print("\nAnalysis complete.")