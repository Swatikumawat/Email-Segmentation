# Framework — Email Nurture Segmentation (dashboard reverse-engineered)

**What this doc is:** a clear map of the existing dashboard page — how it's laid out, what data it shows, what's calculated, and the segmentation logic behind it — plus a check of whether the EASE SAS logic (the back-end thinking) ties up with what the front-end shows. This is the framework we build to.

**Page:** http://3.239.115.25/ → Email Nurture Segmentation (`/model/ease`)
**Data behind it:** `MODEL_DEV.RAW_MKTO`, scored as of 2026-05-28, trailing 24-month window.

---

## 1. How the page is presented

- **Header:** "Email Nurture Segmentation" — *Behavioural personas · engagement rates · sequence performance · cohort & policy*
- **Filter:** Email sent range — All / Last 24m / 12m / 6m / 3m
- **Four tabs:**
  1. **Personas** — the 6 behavioural segments
  2. **Engagement Rates** — open / click / CTOR / unsub, this 12 months vs prior 12
  3. **Sequence Performance** — the 8 nurture programs, each with sends/opens/clicks/rates
  4. **Cohort & Policy** — send-by-send engagement decay + a reactivation funnel + a sales hand-off note
- **Total scored:** 23,574 contacts
- **Caveat shown on page:** "rules-based, gated below 3,000 real contacts — treat as methodology until the live contact base grows."

---

## 2. Tab 1 — Personas (the segmentation itself)

Every contact lands in exactly one of six segments. Each segment carries a size, a confidence score, and a ready-made marketing + sales + tone "playbook."

| Segment | Definition | Size | % | Conf. |
|---|---|---|---|---|
| **Rising Stars** | New · engagement trending up | 1,152 | 4.9% | 0.88 |
| **MVPs** | Sustained high engagement · sales-ready | 3,300 | 14.0% | 0.85 |
| **Hand Raisers** | Opens consistently but rarely clicks | 1,397 | 5.9% | 0.95 |
| **Question Marks** | New · sent to but not opening yet (silent) | 7,051 | 29.9% | 0.88 |
| **Nappers** | Engagement declining · trending dormant | 6,058 | 25.7% | 0.95 |
| **Dormants** | No engagement 90d+ · reactivation candidates | 4,616 | 19.6% | 0.95 |

**Per-segment treatment (this is added IP — not in the SAS):** each segment has 3 marketing actions, 3 sales actions, 3 tone cues, and a `playbook_code`. Example — Dormants: *Marketing:* suppress from active nurture / quarterly reactivation pulse / reallocate budget to Stars. *Sales:* do not pursue / remove from cadences / re-evaluate quarterly. *Tone:* no active messaging / quarterly brand pulse / accept dormancy gracefully.

---

## 3. Tab 2 — Engagement Rates

Four metrics, current 12 months vs prior 12 months, with delta and a good/bad flag:

| Metric | Current | Prior | Δ |
|---|---|---|---|
| Open rate | 32.1% | 31.7% | +0.4 |
| Click rate | 10.0% | 9.9% | +0.1 |
| Click-to-open | 31.2% | 31.3% | −0.1 |
| Unsubscribe | 1.0% | 1.0% | 0.0 |

**Calculation:** opens/sends, clicks/sends, clicks/opens, unsubs/sends — over two rolling 12-month windows.

---

## 4. Tab 3 — Sequence Performance

One row per nurture program (8 total), each with contacts touched, sends, opens, clicks, open rate, click rate, unsub rate. Example: Newsletter-Monthly — 19,688 touched, 59,808 sends, 31.7% open, 10.0% click.

**Calculation:** the same engagement aggregates, grouped by `PRIMARY_ATTR_VALUE` (program name).

---

## 5. Tab 4 — Cohort & Policy

- **Send decay:** for each program, open & click rate by send number (1st send → 6th). Engagement falls every send (e.g. Case-Study: 51.9% → 12.1% open across sends 1–6).
- **Reactivation funnel:** Targeted (dormant) 19,696 → Reactivated (1+ open) 66.1% → Engaged (clicked) 26.3% → Sustained (3+ opens) 5.1%.
- **Hand-off note:** the point where the open-rate curve flattens is where direct sales outreach should take over from nurture.

**Calculation:** uses the `send_no` field inside `ACTIVITIES_RAW.ATTRIBUTES` — engagement rate per send ordinal, per program.

---

## 6. Does the SAS logic tie up with the dashboard? — Mostly YES

| Dashboard element | Comes from EASE SAS? | Notes |
|---|---|---|
| 6 behavioural segments | ✅ Yes — direct evolution | SAS `MARKETING_CAT` = MVC / Rising Stars / Question Marks / Super Stars / Nappers / Dormants. Dashboard merges MVC+Super Stars → **MVPs**, adds **Hand Raisers** (= SAS "opener, not clicker"). Same signals. |
| Recency / frequency / tenure buckets | ✅ Yes | SAS `OPEN/CLICK_RECENCY_CAT`, `EMAILS_*_FREQ_CAT`, `TENURE_CAT` |
| Trend / "lapsing vs reactivating" | ✅ Yes | SAS compares 3M vs 9M vs 2017/2018 windows — same recent-vs-prior idea |
| Open / click / CTOR rates | ✅ Yes | SAS computes these per window |
| Sequence (per-program) breakdown | ➕ New dimension | SAS had campaign data but didn't surface per-program segment views |
| Cohort send-decay + funnel | ➕ New | Uses `send_no`; not in SAS |
| Confidence score + marketing/sales/tone playbooks | ➕ New IP | The "treatment" layer added on top of the segmentation |

**Do the numbers match the data?** Yes — strong confirmation it's computed from `RAW_MKTO`:
- Per-sequence sends match the seed exactly (Newsletter-Monthly = 59,808 in both).
- Rates match our profiling (~32% open, ~10% click).
- Cohort decay uses the real `send_no` attribute.

**One thing that does NOT reconcile (open item for the build):** the personas sum to **23,574** scored contacts, but only **20,000** contacts actually have any activity in `RAW_MKTO`. So their scored universe is ~3,574 wider than "has email activity" — likely some marketable-but-never-sent contacts are folded into Question Marks / Dormants. We'll settle this universe definition when we build (it's the "exclude never-sent vs. keep as a bucket" decision).

---

## 7. What they're looking for (the framework, in one place)

A **contact-grain behavioural segmentation** that:
1. Buckets every contact into one of six segments using **multi-factor** logic — recency × frequency × tenure × **trend** (not one factor).
2. Attaches a **confidence** to each assignment.
3. Attaches a **marketing + sales + tone playbook** per segment.
4. Reports **engagement-rate trends** (12mo vs prior), **per-sequence performance**, and **cohort send-decay + reactivation policy** with a sales hand-off point.
5. Runs off Marketo data, parameterised by score date and sent-range, so it repoints to any client.

That is the target our Python must reproduce and output.
