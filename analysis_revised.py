"""
CMS SynPUF 30-day readmission analysis (revised, Nov 2026).

Readmission definition (simplified, inspired by the CMS measure):
  - Index stay: every inpatient discharge that has a full 30 days of
    follow-up left in the data (discharged on or before 2010-12-01).
  - Readmission: the patient's NEXT admission starts 1 to 30 days after
    that discharge. Gaps of 0 days or less (same-day admissions and
    overlapping claims) are not counted as readmissions.
  - Rate = index stays followed by a readmission / all index stays.
  - Readmission rates by DRG use the DRG of the INDEX stay (the
    condition the patient was discharged with).

Differences from the CMS Hospital-Wide Readmission measure: includes
patients under 65, does not combine transfer chains, applies no
enrollment, death or planned-readmission exclusions, groups by DRG
rather than CMS specialty cohorts, and is not risk adjusted.

The script also re-creates the original (June 2026) method so the two
can be compared side by side.
"""

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

PROJECT = "cms-readmission-analysis"
DATASET = f"{PROJECT}.cms_synpuf"
FOLLOW_UP_CUTOFF = pd.Timestamp("2010-12-01")  # last discharge date with 30 days of follow-up
MIN_DRG_STAYS = 50

FLAGS = ["SP_ALZHDMTA", "SP_CHF", "SP_CHRNKIDN", "SP_CNCR", "SP_COPD", "SP_DEPRESSN",
         "SP_DIABETES", "SP_ISCHMCHT", "SP_OSTEOPRS", "SP_RA_OA", "SP_STRKETIA"]  # all 11

CHECK_QUERY = f"""
SELECT
  COUNT(*) AS n_rows,
  COUNT(DISTINCT CLM_ID) AS n_unique_claims,
  COUNT(DISTINCT DESYNPUF_ID) AS n_patients,
  COUNTIF(CLM_ADMSN_DT IS NULL OR NCH_BENE_DSCHRG_DT IS NULL) AS rows_missing_dates
FROM `{DATASET}.inpatient_claims`
"""


def _bene_select(year):
    cols = ", ".join(FLAGS)
    return (f"SELECT DESYNPUF_ID, BENE_BIRTH_DT, BENE_SEX_IDENT_CD, {cols}, {year} AS bene_year "
            f"FROM `{DATASET}.beneficiary_{year}`")


_flag_sum = " + ".join(f"IF(b.{f} = 1, 1, 0)" for f in FLAGS)  # raw coding: 1 = present, 2 = absent
_prior_flag_sum = " + ".join(f"IF(bp.{f} = 1, 1, 0)" for f in FLAGS)

MAIN_QUERY = f"""
WITH beneficiary AS (
  {_bene_select(2008)}
  UNION ALL
  {_bene_select(2009)}
  UNION ALL
  {_bene_select(2010)}
),
stays AS (
  -- one row per claim: 68 claims are split into a second SEGMENT row; keep segment 1
  SELECT
    DESYNPUF_ID, CLM_ID, CLM_PMT_AMT, CLM_DRG_CD,
    PARSE_DATE('%Y%m%d', CAST(CLM_ADMSN_DT AS STRING)) AS admit_dt,
    PARSE_DATE('%Y%m%d', CAST(NCH_BENE_DSCHRG_DT AS STRING)) AS disch_dt
  FROM `{DATASET}.inpatient_claims`
  WHERE CLM_ADMSN_DT IS NOT NULL AND NCH_BENE_DSCHRG_DT IS NOT NULL
    AND SEGMENT = 1
),
sequenced AS (
  SELECT
    *,
    LEAD(admit_dt) OVER w AS next_admit_dt,   -- looks forward from each discharge
    LAG(disch_dt)  OVER w AS prev_disch_dt    -- looks back (used for the payment comparison)
  FROM stays
  WINDOW w AS (PARTITION BY DESYNPUF_ID ORDER BY admit_dt, disch_dt, CLM_ID)  -- tie-breakers make order deterministic
)
SELECT
  s.DESYNPUF_ID, s.CLM_ID, s.CLM_PMT_AMT, s.CLM_DRG_CD,
  s.admit_dt, s.disch_dt,
  DATE_DIFF(s.next_admit_dt, s.disch_dt, DAY) AS days_to_next_admit,
  DATE_DIFF(s.admit_dt, s.prev_disch_dt, DAY) AS days_since_prev_disch,
  PARSE_DATE('%Y%m%d', CAST(b.BENE_BIRTH_DT AS STRING)) AS birth_dt,
  b.BENE_SEX_IDENT_CD,
  CASE WHEN b.DESYNPUF_ID IS NULL THEN NULL ELSE ({_flag_sum}) END AS chronic_condition_count,
  CASE WHEN bp.DESYNPUF_ID IS NULL THEN NULL ELSE ({_prior_flag_sum}) END AS prior_chronic_count
FROM sequenced s
LEFT JOIN beneficiary b
  ON s.DESYNPUF_ID = b.DESYNPUF_ID
 AND EXTRACT(YEAR FROM s.admit_dt) = b.bene_year
LEFT JOIN beneficiary bp   -- previous year's file, for the robustness check
  ON s.DESYNPUF_ID = bp.DESYNPUF_ID
 AND EXTRACT(YEAR FROM s.admit_dt) - 1 = bp.bene_year
"""


def fetch():
    from google.cloud import bigquery  # imported here so the analysis can be tested offline

    client = bigquery.Client(project=PROJECT)
    checks = client.query(CHECK_QUERY).to_dataframe().iloc[0]
    df = client.query(MAIN_QUERY).to_dataframe()
    return checks, df


def rate_table(frame, by, flag):
    out = frame.groupby(by, observed=True).agg(stays=(flag, "size"), readmits=(flag, "sum")).reset_index()
    out["rate_pct"] = (100 * out["readmits"] / out["stays"]).round(1)
    return out


def run_analysis(checks, df):
    print("=" * 70)
    print("0. DATA CHECKS")
    print(f"   Rows in inpatient_claims:        {int(checks['n_rows']):,}")
    print(f"   Unique claim IDs:                {int(checks['n_unique_claims']):,}")
    print(f"   Unique patients:                 {int(checks['n_patients']):,}")
    print(f"   Rows missing admit/discharge:    {int(checks['rows_missing_dates']):,}")
    print(f"   Claims used after cleaning:      {len(df):,}")

    for col in ["admit_dt", "disch_dt", "birth_dt"]:
        df[col] = pd.to_datetime(df[col])
    df["days_to_next_admit"] = df["days_to_next_admit"].astype(float)
    df["days_since_prev_disch"] = df["days_since_prev_disch"].astype(float)
    df["CLM_PMT_AMT"] = df["CLM_PMT_AMT"].astype(float)

    # ── 1. Original June method, re-created for comparison ────────────────────
    print("\n" + "=" * 70)
    print("1. ORIGINAL METHOD (claims with a prior stay; gap <= 30, incl. 0 and negative)")
    old = df[df["days_since_prev_disch"].notna()].copy()
    old["flag"] = old["days_since_prev_disch"] <= 30
    old["admit_year"] = old["admit_dt"].dt.year
    print(f"   Denominator: {len(old):,}   Readmissions: {int(old['flag'].sum()):,}   "
          f"Rate: {100 * old['flag'].mean():.1f}%")
    print(f"   Of those 'readmissions', gap of 0 days or less (not real readmissions): "
          f"{int((old['days_since_prev_disch'] <= 0).sum()):,}")
    print(rate_table(old, "admit_year", "flag").to_string(index=False))

    # ── 2. Revised method ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("2. REVISED METHOD (per index discharge, next admission 1-30 days later)")
    idx = df[df["disch_dt"] <= FOLLOW_UP_CUTOFF].copy()
    idx["readmit_30d"] = idx["days_to_next_admit"].between(1, 30)
    idx["discharge_year"] = idx["disch_dt"].dt.year
    overlap = int((idx["days_to_next_admit"] <= 0).sum())
    print(f"   Index discharges: {len(idx):,}   Readmitted within 30 days: {int(idx['readmit_30d'].sum()):,}   "
          f"Rate: {100 * idx['readmit_30d'].mean():.1f}%")
    print(f"   Next stay starts same day or overlaps (excluded): {overlap:,}")
    print("\n   By discharge year:")
    print(rate_table(idx, "discharge_year", "readmit_30d").to_string(index=False))
    print("\n   Claim volume by admission year (tests the 'falling volume' explanation):")
    print(df.groupby(df["admit_dt"].dt.year).size().to_string())

    drg = rate_table(idx, "CLM_DRG_CD", "readmit_30d")
    drg = drg[drg["stays"] >= MIN_DRG_STAYS].sort_values("rate_pct", ascending=False).head(10)
    print(f"\n   Top 10 index-stay DRGs (min {MIN_DRG_STAYS} stays):")
    print(drg.to_string(index=False))

    # ── 3. Patient characteristics (index stays matched to a beneficiary file) ─
    print("\n" + "=" * 70)
    print("3. PATIENT CHARACTERISTICS (index stays)")
    pat = idx[idx["birth_dt"].notna()].copy()
    pat["age"] = np.floor((pat["admit_dt"] - pat["birth_dt"]).dt.days / 365.25)
    pat["age_band"] = pd.cut(pat["age"], bins=[0, 65, 75, 85, 200],
                             labels=["Under 65", "65-74", "75-84", "85+"], right=False)
    pat["sex"] = pat["BENE_SEX_IDENT_CD"].map({1: "Male", 2: "Female"})
    print(f"   Index stays with a beneficiary match: {len(pat):,} of {len(idx):,}")
    ages = rate_table(pat, "age_band", "readmit_30d")
    ccs = rate_table(pat, "chronic_condition_count", "readmit_30d")
    sexes = rate_table(pat, "sex", "readmit_30d")
    print("\n   By age band:\n" + ages.to_string(index=False))
    print("\n   By chronic condition count (0-11):\n" + ccs.to_string(index=False))
    pat["cc_group"] = pd.cut(pat["chronic_condition_count"], bins=[-1, 2, 5, 8, 11],
                             labels=["0-2", "3-5", "6-8", "9-11"])
    print("\n   By chronic condition group:\n" + rate_table(pat, "cc_group", "readmit_30d").to_string(index=False))
    print("\n   By sex:\n" + sexes.to_string(index=False))

    # ── 4. Payment: readmission stays vs all other stays ──────────────────────
    print("\n" + "=" * 70)
    print("4. PAYMENT: readmission stays (began 1-30 days after a discharge) vs all other stays")
    pay = df[df["CLM_PMT_AMT"].notna()].copy()
    pay["is_readmission_stay"] = pay["days_since_prev_disch"].between(1, 30)
    a = pay.loc[pay["is_readmission_stay"], "CLM_PMT_AMT"]
    b = pay.loc[~pay["is_readmission_stay"], "CLM_PMT_AMT"]
    diff = a.mean() - b.mean()
    print(f"   Readmission stays: n={len(a):,}  mean=${a.mean():,.0f}  median=${a.median():,.0f}")
    print(f"   Other stays:       n={len(b):,}  mean=${b.mean():,.0f}  median=${b.median():,.0f}")
    print(f"   Mean difference: ${diff:,.0f} ({100 * diff / b.mean():.1f}% of other-stay mean)")
    print(f"   Payments <= $0 in data: {int((pay['CLM_PMT_AMT'] <= 0).sum()):,}")
    welch = stats.ttest_ind(a, b, equal_var=False)
    mwu = stats.mannwhitneyu(a, b, alternative="two-sided")
    a_pos, b_pos = a[a > 0], b[b > 0]
    welch_log = stats.ttest_ind(np.log(a_pos), np.log(b_pos), equal_var=False)
    print(f"   Welch t-test (unequal variances):  p = {welch.pvalue:.2e}")
    print(f"   Mann-Whitney U (no normality):     p = {mwu.pvalue:.2e}")
    print(f"   Welch t-test on log(payment > 0):  p = {welch_log.pvalue:.2e}")

    # Same patient, readmission stays vs their own other stays (removes "sicker patients" effect)
    within = pay.groupby(["DESYNPUF_ID", "is_readmission_stay"])["CLM_PMT_AMT"].mean().unstack().dropna()
    w_diff = (within[True] - within[False]).mean()
    w_t = stats.ttest_rel(within[True], within[False])
    w_wx = stats.wilcoxon(within[True], within[False])
    w = within[True] - within[False]
    print(f"   Within-patient: {len(within):,} patients, mean diff ${w_diff:,.0f}, "
          f"median diff ${w.median():,.0f}")
    print(f"      Readmission stay cheaper for {int((w < 0).sum()):,} patients, "
          f"more expensive for {int((w > 0).sum()):,}")
    print(f"      Paired t p = {w_t.pvalue:.2e}, Wilcoxon p = {w_wx.pvalue:.2e}")
    print(f"   Payments that are multiples of $1,000: {100 * (pay['CLM_PMT_AMT'] % 1000 == 0).mean():.1f}%")

    # ── 4b. Robustness: chronic conditions from the PREVIOUS year's file ──────
    # Same-year flags are built from the same year's claims, so they can
    # reflect the index stay itself. Prior-year flags avoid that.
    print("\n" + "=" * 70)
    print("4b. CHRONIC CONDITIONS FROM THE PRIOR YEAR (2009-2010 index stays only)")
    prior = idx[idx["prior_chronic_count"].notna()].copy()
    prior["cc_group"] = pd.cut(prior["prior_chronic_count"], bins=[-1, 2, 5, 8, 11],
                               labels=["0-2", "3-5", "6-8", "9-11"])
    print(f"   Index stays with a prior-year match: {len(prior):,}")
    print(rate_table(prior, "cc_group", "readmit_30d").to_string(index=False))

    # ── 5. Charts ─────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle("CMS SynPUF 30-Day Readmission Analysis (revised method)", fontsize=14, fontweight="bold")
    ax = axes.flatten()

    old_y = rate_table(old, "admit_year", "flag")
    new_y = rate_table(idx, "discharge_year", "readmit_30d")
    old_y = old_y[old_y["admit_year"].between(2008, 2010)]
    new_y = new_y[new_y["discharge_year"].between(2008, 2010)]
    x = np.arange(len(new_y))
    ax[0].bar(x - 0.2, old_y["rate_pct"].values[: len(x)], 0.4, label="Original method", color="lightgray")
    ax[0].bar(x + 0.2, new_y["rate_pct"].values, 0.4, label="Revised method", color="steelblue")
    ax[0].set_xticks(x, new_y["discharge_year"].astype(str))
    ax[0].set_title("Rate by year: original (admission yr) vs revised (discharge yr)", fontsize=10)
    ax[0].set_ylabel("Rate (%)")
    ax[0].legend()

    ax[1].boxplot([b_pos, a_pos], tick_labels=["Other stays", "Readmission stays"])
    ax[1].set_yscale("log")
    ax[1].set_title("Payment per stay (log scale)")
    ax[1].set_ylabel("Payment ($)")

    ax[2].barh(drg["CLM_DRG_CD"].astype(str), drg["rate_pct"], color="coral")
    ax[2].invert_yaxis()
    ax[2].set_title("Top index-stay DRGs by readmission rate")
    ax[2].set_xlabel("Rate (%)")

    ax[3].bar(ages["age_band"].astype(str), ages["rate_pct"], color="mediumpurple")
    ax[3].set_title("By age band")
    ax[3].set_ylabel("Rate (%)")

    ax[4].bar(ccs["chronic_condition_count"].astype(int).astype(str), ccs["rate_pct"], color="teal")
    ax[4].set_title("By chronic condition count")
    ax[4].set_ylabel("Rate (%)")

    ax[5].bar(sexes["sex"], sexes["rate_pct"], color="goldenrod")
    ax[5].set_title("By sex")
    ax[5].set_ylabel("Rate (%)")

    plt.tight_layout()
    plt.savefig("readmission_analysis.png", dpi=150, bbox_inches="tight")
    print("\nChart saved to readmission_analysis.png")


if __name__ == "__main__":
    run_analysis(*fetch())
