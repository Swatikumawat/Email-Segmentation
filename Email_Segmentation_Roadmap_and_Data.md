# Email Nurture Segmentation — Roadmap & Data Identification

**Project:** Email Nurture Segmentation (EASE) — Transmission CDP Model
**Source of truth for *logic*:** the EASE SAS code (reference blueprint only — we **replace** it with Python).
**Source of *data*:** `MODEL_DEV.RAW_MKTO` (seeded dummy Marketo Engage data).
**Target:** produce the output the Model Platform dashboard consumes (`/transmission/api/segment/ease/overview`). How the dashboard is *currently* populated is out of scope — we assume we are dropping a fresh segmentation behind the same page.
**Language:** Python (parameterised; no hardcoded credentials or dates).

---

## Approach in one paragraph

The EASE SAS model is a deterministic, **multi-factor** engagement-segmentation engine (RFM-style: recency, frequency, tenure + behavioural transitions). We reproduce *that thinking* — not the SAS — in Python, computing per-contact engagement features from `RAW_MKTO` and bucketing every marketable contact into one of six behavioural segments with a confidence score, shaped to the dashboard contract. The same code repoints at a real client's Marketo data at go-live.

## Roadmap (two tracks)

**Track 1 — Data identification** *(this document)*
1. Profile the seeded `RAW_MKTO` tables — fields, types, distributions. ✅
2. Document real-Marketo fields vs. the dummy data — the gap and what to request from a client. ✅
3. Define the per-contact feature set the algo computes. ✅ (below)

**Track 2 — Segmentation logic** *(next)*
4. Multi-factor feature engine — recency, frequency, tenure, **and trend/transition** over trailing windows.
5. Bucketing rules → 6 segments + confidence.
6. Python implementation, output shaped to the dashboard contract.

---

## Step 1 findings — seeded data dictionary (live, as of 2026-05-30)

### `LEADS_RAW` — 126,440 contacts (the people)
| Column | Type | Notes |
|---|---|---|
| `LEAD_ID` | NUMBER | join key to activities |
| `EMAIL` | VARCHAR | identity |
| `UNSUBSCRIBED` | BOOLEAN | **122,663 FALSE (marketable) / 3,777 TRUE** |
| `ATTRIBUTES` | VARIANT | **empty `{}` for all rows** in the seed |
| `_INGESTED_AT` | TIMESTAMP | load metadata |

### `ACTIVITIES_RAW` — 679,315 events across 20,000 contacts
| Column | Type | Notes |
|---|---|---|
| `ACTIVITY_ID` | NUMBER | event id |
| `LEAD_ID` | NUMBER | → LEADS_RAW |
| `ACTIVITY_DATE` | TIMESTAMP | 2024-06-05 → 2026-05-30 (2-yr window) |
| `ACTIVITY_TYPE_ID` | NUMBER | **6 Send (475,915) · 10 Open (151,365) · 11 Click (47,294) · 9 Unsubscribe (4,741)** |
| `PRIMARY_ATTR_VALUE` | VARCHAR | program name (8 programs) |
| `PRIMARY_ATTR_VALUE_ID` | NUMBER | program id |
| `CAMPAIGN_ID` | NUMBER | campaign id |
| `ATTRIBUTES` | VARIANT | only `{ "send_no": N }` in the seed |
| `_INGESTED_AT`, `_SOURCE_BATCH_ID` | — | load metadata |

### `EMAIL_ASSETS_RAW` — **empty** (ASSET_ID, SUBJECT, FROM_NAME, FROM_EMAIL, ATTRIBUTES, _INGESTED_AT)

### Per-contact engagement profile (the 20,000 active contacts)
- Sends: avg **23.8**, median 24, max 37 · Opens: avg 7.6 · Clicks: avg 2.4
- Open rate avg **31.8%** · Click rate avg **9.9%**
- Recency (days since last activity): avg **40**, median 32
- Tenure (months since first activity): avg **22.1**
- Zero-open contacts: 5 · Zero-click contacts: 1,782 (8.9%)
- Recency bands: ≤30d **9,461** · 31–90d **9,256** · >90d (dormant) **1,283**

### Universe note (a decision for Track 2)
Only **20,000 of 122,663 marketable contacts have any email activity** in the seed. The other ~102k were never sent to. Per EASE, the scored universe = contacts who received ≥1 email. The never-sent population is either excluded or held as a separate "no-data" bucket — to confirm in Track 2.

---

## Step 1 findings — real Marketo vs. the dummy data (the "data points you need")

The seed is a deliberately thin slice. Real Marketo (REST API / Bulk Extract) exposes far more, and several missing fields would materially strengthen segmentation. **This is the list to request from a client at go-live.**

| Signal | In seed? | Real Marketo source | Why it matters for segmentation |
|---|---|---|---|
| Sends / Opens / Clicks | ✅ | Activity types 6 / 10 / 11 | core RFM engine |
| Unsubscribe | ✅ | Activity type 9 + `unsubscribed` field | suppression |
| **True opt-in / created date** | ❌ (ATTRIBUTES empty) | Lead field `createdAt` | real tenure; seed forces a **first-activity-date proxy** |
| **Email Delivered / Bounced** | ❌ (no type 7/8) | Activity types 7, 8; `emailInvalid` | true deliverability vs. send |
| **Lead score / behaviour score** | ❌ | `leadScore`, `relativeScore`, `urgency` | ready-made intent signal |
| **Job title / seniority / dept** | ❌ | Lead demographic fields | B2B fit + persona |
| **Company / country / industry** | ❌ | Lead + inferred firmographics | account context, ABM |
| **Lead status / lifecycle stage** | ❌ | `leadStatus`, lifecycle fields | funnel position |
| **Web visits / form fills / link clicks** | ❌ (only email) | Activity types 1, 2, 3 | engagement beyond email (B2B analog of EASE's non-email value signals) |
| **Email client / device** | ❌ | Email activity attributes | engagement quality, deliverability |
| **Asset / subject metadata** | ❌ (EMAIL_ASSETS_RAW empty) | `EMAIL_ASSETS_RAW` / asset API | content-affinity segmentation |

**Two substitutions we will make in the build (and state explicitly):**
1. **Tenure** — no opt-in date → use each contact's **first activity date** as the months-on-file proxy.
2. **Deliverability** — no bounce events → treat **not-unsubscribed** as deliverable.

---

## Proposed per-contact feature set (input to the segmentation engine)

Computed per `LEAD_ID` as of a parameterised **score date**, over trailing windows (3M / 9M / 12M / 24M):

- **Volume:** sends, opens, clicks (per window + lifetime)
- **Rates:** open rate, click rate, click-to-open rate (CTOR)
- **Recency:** days since last open / click / any activity
- **Frequency:** email velocity (sends per active month)
- **Tenure:** months on file (first-activity proxy)
- **Trend / transition (the multi-factor differentiator):** engagement in recent window vs. prior window — e.g. dormant in prior 90d but active in last 30d → *reactivating*; declining open rate → *lapsing*.

These features feed the Track 2 bucketing rules that assign each contact to one of the six segments (Rising Star, MVP, Hand Raiser, Question Mark, Napper, Dormant) with a confidence score.
