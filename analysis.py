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
WITH ordered_claims AS (
  SELECT
    DESYNPUF_ID,
    CLM_ADMSN_DT,
    NCH_BENE_DSCHRG_DT,
    CLM_PMT_AMT,
    CLM_DRG_CD,
    LAG(NCH_BENE_DSCHRG_DT) OVER (
      PARTITION BY DESYNPUF_ID ORDER BY CLM_ADMSN_DT
    ) AS prev_discharge_dt
  FROM `cms-readmission-analysis.cms_synpuf.inpatient_claims`
),
readmissions AS (
  SELECT
    DESYNPUF_ID,
    CLM_ADMSN_DT,
    NCH_BENE_DSCHRG_DT,
    CLM_PMT_AMT,
    CLM_DRG_CD,
    CASE
      WHEN DATE_DIFF(
        PARSE_DATE('%Y%m%d', CAST(CLM_ADMSN_DT AS STRING)),
        PARSE_DATE('%Y%m%d', CAST(prev_discharge_dt AS STRING)),
        DAY
      ) <= 30 THEN 1
      ELSE 0
    END AS is_readmission
  FROM ordered_claims
  WHERE prev_discharge_dt IS NOT NULL
)
SELECT * FROM readmissions
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

# ── 5. Visualizations ─────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(15, 5))
fig.suptitle('CMS SynPUF Medicare Readmission Analysis', fontsize=14, fontweight='bold')

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

plt.tight_layout()
plt.savefig('readmission_analysis.png', dpi=150, bbox_inches='tight')
print("\nVisualization saved to readmission_analysis.png")
print("\nAnalysis complete.")