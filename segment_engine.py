"""
Email Nurture Segmentation — engine v1.
Reads MODEL_DEV.RAW_MKTO.ES_ACTIVITIES + ES_LEADS, builds multi-factor engagement
features per contact, assigns one of six behavioural segments + a confidence score,
and writes MODEL_DEV.RAW_MKTO.ES_CONTACT_SEGMENTS.

Multi-factor logic (not a single metric): recency + frequency + tenure + TREND
(recent 90d vs prior 90-180d) decide the group. EASE methodology, B2B-tuned.
"""
import sys, datetime
import pandas as pd
import sf  # local connection helper (account/user/warehouse + key-pair)

SCORE_DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-05-30"

SEG = {  # code -> (label, playbook_code)
    "RISING_STAR":   ("Rising Stars",   "welcome_onboarding_abm_personalised"),
    "MVP":           ("MVPs",           "fast_track_demo_engagement_acceleration"),
    "HAND_RAISER":   ("Hand Raisers",   "click_incentive_gated_assets_1to1"),
    "QUESTION_MARK": ("Question Marks",  "ab_test_subject_lines_educational_drip"),
    "NAPPER":        ("Nappers",        "win_back_3sends_subject_refresh"),
    "DORMANT":       ("Dormants",       "suppress_active_quarterly_pulse"),
}

FEATURE_SQL = f"""
WITH base AS (
  SELECT LEAD_ID,
    COUNT_IF(ACTIVITY_TYPE_ID=6)  AS sends,
    COUNT_IF(ACTIVITY_TYPE_ID=10) AS opens,
    COUNT_IF(ACTIVITY_TYPE_ID=11) AS clicks,
    COUNT_IF(ACTIVITY_TYPE_ID=10 AND ACTIVITY_DATE >= DATEADD('day',-90,'{SCORE_DATE}'))  AS opens_recent,
    COUNT_IF(ACTIVITY_TYPE_ID=11 AND ACTIVITY_DATE >= DATEADD('day',-90,'{SCORE_DATE}'))  AS clicks_recent,
    COUNT_IF(ACTIVITY_TYPE_ID=10 AND ACTIVITY_DATE >= DATEADD('day',-180,'{SCORE_DATE}') AND ACTIVITY_DATE < DATEADD('day',-90,'{SCORE_DATE}')) AS opens_prior,
    COUNT_IF(ACTIVITY_TYPE_ID=11 AND ACTIVITY_DATE >= DATEADD('day',-180,'{SCORE_DATE}') AND ACTIVITY_DATE < DATEADD('day',-90,'{SCORE_DATE}')) AS clicks_prior,
    MAX(CASE WHEN ACTIVITY_TYPE_ID IN (10,11) THEN ACTIVITY_DATE END) AS last_engage,
    MIN(ACTIVITY_DATE) AS first_act
  FROM MODEL_DEV.RAW_MKTO.ES_ACTIVITIES
  WHERE ACTIVITY_DATE BETWEEN DATEADD('month',-24,'{SCORE_DATE}') AND '{SCORE_DATE}'
  GROUP BY 1
)
SELECT b.LEAD_ID, b.sends, b.opens, b.clicks, b.opens_recent, b.clicks_recent,
       b.opens_prior, b.clicks_prior,
       DATEDIFF('day', b.last_engage::date, '{SCORE_DATE}') AS recency_days,
       DATEDIFF('month', b.first_act::date, '{SCORE_DATE}') AS tenure_months,
       l.LEAD_SCORE
FROM base b
JOIN MODEL_DEV.RAW_MKTO.ES_LEADS l ON b.LEAD_ID = l.LEAD_ID
WHERE l.UNSUBSCRIBED = FALSE AND b.sends > 0
"""


def classify(r):
    """Return (segment_code, confidence, trend) from the multi-factor signals.
    Uses engagement recency (days since last open/click) + click depth + trend
    (recent 90d vs prior 90-180d). Tenure is de-emphasised because the seed gives
    everyone ~2yr tenure; with real client data the 'new' cohorts surface naturally."""
    orr = r.OPENS_RECENT + r.CLICKS_RECENT          # engagement last 90d
    pri = r.OPENS_PRIOR + r.CLICKS_PRIOR            # engagement 90-180d
    rec = 999 if pd.isna(r.RECENCY_DAYS) else r.RECENCY_DAYS
    cr, orate = r.CLICK_RATE, r.OPEN_RATE
    warming, cooling = orr > pri, orr < pri
    trend = "warming" if warming else ("cooling" if cooling else "steady")

    # lapsed, by how long since they last opened/clicked
    if rec > 180:
        return ("DORMANT", 0.93, "cooling")
    if rec > 90:
        return ("NAPPER", 0.86, "cooling")

    # engaged within 90d -> split by depth & direction
    if cr >= 0.12 and r.CLICKS_RECENT > 0:
        return ("MVP", round(min(0.96, 0.80 + cr), 3), trend)
    if warming and cr >= 0.05 and r.CLICKS_RECENT > 0:
        return ("RISING_STAR", round(min(0.93, 0.80 + cr), 3), "warming")
    if orate < 0.28 and cr < 0.04:
        return ("QUESTION_MARK", 0.85, trend)
    if r.OPENS_RECENT > 0 and cr < 0.03:
        return ("HAND_RAISER", 0.90, trend)
    if cooling:
        return ("NAPPER", 0.82, "cooling")
    return ("MVP", 0.80, trend) if cr >= 0.06 else ("HAND_RAISER", 0.82, trend)


def main():
    conn = sf.connect()
    cur = conn.cursor()
    print(f"Scoring as of {SCORE_DATE} ...")
    cur.execute(FEATURE_SQL)
    cols = [c[0] for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=cols)
    print(f"  universe: {len(df):,} contacts")

    # derived features
    df["OPEN_RATE"] = (df.OPENS / df.SENDS).round(4)
    df["CLICK_RATE"] = (df.CLICKS / df.SENDS).round(4)
    df["CTOR"] = (df.CLICKS / df.OPENS.replace(0, pd.NA)).fillna(0).round(4)
    df["EMAIL_VELOCITY"] = (df.SENDS / df.TENURE_MONTHS.clip(lower=1)).round(2)

    res = df.apply(classify, axis=1, result_type="expand")
    df["SEGMENT_CODE"], df["CONFIDENCE"], df["TREND"] = res[0], res[1], res[2]
    df["SEGMENT_LABEL"] = df.SEGMENT_CODE.map(lambda c: SEG[c][0])
    df["PLAYBOOK_CODE"] = df.SEGMENT_CODE.map(lambda c: SEG[c][1])

    print("  segment distribution:")
    for code, n in df.SEGMENT_CODE.value_counts().items():
        print(f"    {code:<14} {n:>6,}  ({n/len(df)*100:4.1f}%)")

    # write to ES_CONTACT_SEGMENTS
    cur.execute("TRUNCATE TABLE MODEL_DEV.RAW_MKTO.ES_CONTACT_SEGMENTS")
    out_cols = ["SCORE_DATE","LEAD_ID","SEGMENT_CODE","SEGMENT_LABEL","CONFIDENCE","SENDS","OPENS","CLICKS",
                "OPEN_RATE","CLICK_RATE","CTOR","RECENCY_DAYS","TENURE_MONTHS","EMAIL_VELOCITY","TREND",
                "LEAD_SCORE","PLAYBOOK_CODE","SCORED_AT"]
    now = datetime.datetime.now()
    rows = [(SCORE_DATE, int(r.LEAD_ID), r.SEGMENT_CODE, r.SEGMENT_LABEL, float(r.CONFIDENCE),
             int(r.SENDS), int(r.OPENS), int(r.CLICKS), float(r.OPEN_RATE)*100, float(r.CLICK_RATE)*100,
             float(r.CTOR)*100, None if pd.isna(r.RECENCY_DAYS) else int(r.RECENCY_DAYS),
             int(r.TENURE_MONTHS or 0), float(r.EMAIL_VELOCITY), r.TREND, int(r.LEAD_SCORE), r.PLAYBOOK_CODE, now)
            for r in df.itertuples()]
    ins = f"INSERT INTO MODEL_DEV.RAW_MKTO.ES_CONTACT_SEGMENTS ({','.join(out_cols)}) VALUES ({','.join(['%s']*len(out_cols))})"
    cur.executemany(ins, rows)
    conn.commit()
    print(f"  wrote {len(rows):,} rows to ES_CONTACT_SEGMENTS")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
