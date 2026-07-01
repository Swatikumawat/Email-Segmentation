"""
Email Nurture Segmentation — POC dashboard.
Flask API over MODEL_DEV.RAW_MKTO.ES_CONTACT_SEGMENTS + ES_ACTIVITIES,
Transmission-styled front-end (4 tabs: Personas, Engagement Rates, Sequence, Cohort).
Run:  python dashboard.py   ->  http://127.0.0.1:5000
"""
import datetime, decimal
from flask import Flask, jsonify, Response
import sf

app = Flask(__name__)
SCORE = "2026-05-30"


def _coerce(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return v


def run(sql):
    conn = sf.connect(); cur = conn.cursor()
    try:
        cur.execute(sql)
        cols = [c[0].lower() for c in cur.description]
        return [{c: _coerce(v) for c, v in zip(cols, row)} for row in cur.fetchall()]
    finally:
        cur.close(); conn.close()


TREAT = {
 "RISING_STAR": {"desc": "New / momentum building · engagement trending up",
   "marketing": ["Welcome + onboarding drip", "ABM personalised content", "Fast-track to demo sequence"],
   "sales": ["Prioritise in daily call list", "AE-led multi-thread", "Executive sponsor mapping"],
   "tone": ["Warm, momentum-building", "You're off to a great start", "Outcome-led, fast to value"]},
 "MVP": {"desc": "Sustained high engagement · sales-ready",
   "marketing": ["Engagement acceleration", "Case study + ROI nurture", "Content-syndication retarget"],
   "sales": ["BDR follow-up on clicks", "Standard cadence + timing", "Upsell / cross-sell triggers"],
   "tone": ["ROI + competitive proof", "Direct business case", "Personalised to use case"]},
 "HAND_RAISER": {"desc": "Opens consistently but rarely clicks",
   "marketing": ["Click-incentive sequences", "Re-engage with gated assets", "A/B test subject lines"],
   "sales": ["Monitor for click conversion", "Offer 1:1 content preview", "Flag if no click after 3 sends"],
   "tone": ["Curiosity-driven, low friction", "See what you're missing", "Educational, not salesy"]},
 "QUESTION_MARK": {"desc": "Barely engaging · sent but not opening much yet",
   "marketing": ["Light educational drip", "Low-frequency awareness", "Monitor for engagement spike"],
   "sales": ["No outbound yet", "Track for segment migration", "Re-tier if engagement rises"],
   "tone": ["Gentle awareness", "Category-level content", "No product pitch yet"]},
 "NAPPER": {"desc": "Engagement declining · trending dormant",
   "marketing": ["Win-back sequence (3 sends)", "Subject-line refresh", "Reduce frequency to biweekly"],
   "sales": ["Re-engage with personal note", "Check CRM for stale opps", "Escalate if high-value account"],
   "tone": ["Urgency + value reminder", "We noticed you've been quiet", "Fresh angle, not repetition"]},
 "DORMANT": {"desc": "No engagement 90d+ · reactivation candidate",
   "marketing": ["Suppress from active nurture", "Quarterly reactivation pulse", "Reallocate budget to Stars"],
   "sales": ["Do not pursue", "Remove from active cadences", "Re-evaluate quarterly only"],
   "tone": ["No active messaging", "Quarterly brand pulse only", "Accept dormancy gracefully"]},
}
ORDER = ["RISING_STAR", "MVP", "HAND_RAISER", "QUESTION_MARK", "NAPPER", "DORMANT"]


def build_overview():
    segs = run("""SELECT SEGMENT_CODE code, SEGMENT_LABEL label, COUNT(*) n, AVG(CONFIDENCE)::float conf,
        AVG(OPEN_RATE)::float open_rate, AVG(CLICK_RATE)::float click_rate, AVG(RECENCY_DAYS)::float recency,
        AVG(LEAD_SCORE)::float lead_score FROM MODEL_DEV.RAW_MKTO.ES_CONTACT_SEGMENTS GROUP BY 1,2""")
    total = sum(s["n"] for s in segs) or 1
    by = {s["code"]: s for s in segs}
    personas = []
    for code in ORDER:
        s = by.get(code)
        if not s:
            continue
        t = TREAT[code]
        personas.append({"segment": code, "label": s["label"], "desc": t["desc"], "n": s["n"],
            "pct": round(s["n"] / total, 3), "confidence": round(s["conf"], 2),
            "open_rate": round(s["open_rate"], 1), "click_rate": round(s["click_rate"], 1),
            "recency": round(s["recency"]), "lead_score": round(s["lead_score"]),
            "marketing": t["marketing"], "sales": t["sales"], "tone": t["tone"]})

    r = run(f"""SELECT
        COUNT_IF(ACTIVITY_TYPE_ID=6  AND ACTIVITY_DATE>=DATEADD('month',-12,'{SCORE}')) cs,
        COUNT_IF(ACTIVITY_TYPE_ID=10 AND ACTIVITY_DATE>=DATEADD('month',-12,'{SCORE}')) co,
        COUNT_IF(ACTIVITY_TYPE_ID=11 AND ACTIVITY_DATE>=DATEADD('month',-12,'{SCORE}')) cc,
        COUNT_IF(ACTIVITY_TYPE_ID=9  AND ACTIVITY_DATE>=DATEADD('month',-12,'{SCORE}')) cu,
        COUNT_IF(ACTIVITY_TYPE_ID=6  AND ACTIVITY_DATE< DATEADD('month',-12,'{SCORE}')) ps,
        COUNT_IF(ACTIVITY_TYPE_ID=10 AND ACTIVITY_DATE< DATEADD('month',-12,'{SCORE}')) po,
        COUNT_IF(ACTIVITY_TYPE_ID=11 AND ACTIVITY_DATE< DATEADD('month',-12,'{SCORE}')) pc,
        COUNT_IF(ACTIVITY_TYPE_ID=9  AND ACTIVITY_DATE< DATEADD('month',-12,'{SCORE}')) pu
        FROM MODEL_DEV.RAW_MKTO.ES_ACTIVITIES WHERE ACTIVITY_DATE>=DATEADD('month',-24,'{SCORE}')""")[0]
    def rate(n, d): return round(100 * n / d, 1) if d else 0.0
    rates = []
    for name, cn, cd, pn, pd_, good_up in [
        ("Open rate", r["co"], r["cs"], r["po"], r["ps"], True),
        ("Click rate", r["cc"], r["cs"], r["pc"], r["ps"], True),
        ("Click-to-open", r["cc"], r["co"], r["pc"], r["po"], True),
        ("Unsubscribe", r["cu"], r["cs"], r["pu"], r["ps"], False)]:
        cur_, pri_ = rate(cn, cd), rate(pn, pd_)
        d = round(cur_ - pri_, 1)
        rates.append({"metric": name, "current": cur_, "prior": pri_, "delta": d,
                      "good": (d >= 0) if good_up else (d <= 0)})

    seq = run("""SELECT PRIMARY_ATTR_VALUE program,
        COUNT(DISTINCT CASE WHEN ACTIVITY_TYPE_ID=6 THEN LEAD_ID END) touched,
        COUNT_IF(ACTIVITY_TYPE_ID=6) sends, COUNT_IF(ACTIVITY_TYPE_ID=10) opens,
        COUNT_IF(ACTIVITY_TYPE_ID=11) clicks, COUNT_IF(ACTIVITY_TYPE_ID=9) unsub
        FROM MODEL_DEV.RAW_MKTO.ES_ACTIVITIES GROUP BY 1 ORDER BY sends DESC""")
    for s in seq:
        s["open_rate"] = rate(s["opens"], s["sends"]); s["click_rate"] = rate(s["clicks"], s["sends"])
        s["unsub_rate"] = rate(s["unsub"], s["sends"])

    decay = run("""SELECT ATTRIBUTES:send_no::int send_no, COUNT_IF(ACTIVITY_TYPE_ID=6) sends,
        COUNT_IF(ACTIVITY_TYPE_ID=10) opens, COUNT_IF(ACTIVITY_TYPE_ID=11) clicks
        FROM MODEL_DEV.RAW_MKTO.ES_ACTIVITIES WHERE ATTRIBUTES:send_no IS NOT NULL GROUP BY 1 ORDER BY 1""")
    for d in decay:
        d["open_rate"] = rate(d["opens"], d["sends"]); d["click_rate"] = rate(d["clicks"], d["sends"])

    f = run(f"""SELECT
        COUNT(DISTINCT CASE WHEN ACTIVITY_TYPE_ID=6 THEN LEAD_ID END) sent,
        COUNT(DISTINCT CASE WHEN ACTIVITY_TYPE_ID=10 THEN LEAD_ID END) opened,
        COUNT(DISTINCT CASE WHEN ACTIVITY_TYPE_ID=11 THEN LEAD_ID END) clicked
        FROM MODEL_DEV.RAW_MKTO.ES_ACTIVITIES WHERE ACTIVITY_DATE>=DATEADD('day',-90,'{SCORE}')""")[0]
    sus = run(f"""SELECT COUNT(*) n FROM (SELECT LEAD_ID FROM MODEL_DEV.RAW_MKTO.ES_ACTIVITIES
        WHERE ACTIVITY_TYPE_ID=10 AND ACTIVITY_DATE>=DATEADD('day',-90,'{SCORE}') GROUP BY 1 HAVING COUNT(*)>=3)""")[0]["n"]
    base = f["sent"] or 1
    funnel = [{"outcome": "Sent (90d)", "n": f["sent"], "pct": 1.0},
              {"outcome": "Opened", "n": f["opened"], "pct": round(f["opened"]/base, 3)},
              {"outcome": "Clicked", "n": f["clicked"], "pct": round(f["clicked"]/base, 3)},
              {"outcome": "Sustained (3+ opens)", "n": sus, "pct": round(sus/base, 3)}]

    return {"total": total, "score_date": SCORE, "personas": personas, "rates": rates,
            "sequence": seq, "decay": decay, "funnel": funnel}


@app.route("/api/ease/overview")
def api_overview():
    return jsonify(build_overview())


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html")


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Email Nurture Segmentation · Transmission</title>
<style>
@font-face{font-family:'AvenirNext';src:url('https://transmission-apps.com/fonts/AvenirNextRegular/font.woff2') format('woff2');font-weight:400;font-display:block}
@font-face{font-family:'AvenirNext';src:url('https://transmission-apps.com/fonts/AvenirNextMedium/font.woff2') format('woff2');font-weight:600;font-display:block}
@font-face{font-family:'AvenirNext';src:url('https://transmission-apps.com/fonts/AvenirNextBold/font.woff2') format('woff2');font-weight:700;font-display:block}
:root{--bg:#222;--bg2:#1a1a1a;--surface:#2a2a2a;--elev:#333;--border:#3a3a3a;--border2:#444;
--fg:#fff;--muted:#bbb;--dim:#888;--blue:#96d0d3;--pink:#e12c86;--green:#4caf82;--red:#e05c5c;--amber:#ffb432;
--font:'AvenirNext','Avenir Next LT Pro','Century Gothic',system-ui,sans-serif;--caps:0.06em}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font-family:var(--font);font-size:15px;display:flex;min-height:100vh}
.sidebar{width:220px;background:var(--bg2);border-right:1px solid #2e2e2e;padding:22px 0;flex-shrink:0}
.sidebar .logo{padding:0 22px 26px}
.sidebar .seclabel{font-size:13px;font-weight:700;letter-spacing:var(--caps);text-transform:uppercase;color:var(--dim);padding:0 22px 10px}
.sidebar a{display:block;padding:9px 22px;color:var(--muted);font-size:15px;border-left:3px solid transparent;cursor:pointer}
.sidebar a.active{color:var(--fg);border-left-color:var(--blue);background:#202020}
.main{flex:1;padding:32px 40px;max-width:1180px}
.eyebrow{font-size:13px;font-weight:700;letter-spacing:var(--caps);text-transform:uppercase;color:var(--blue)}
h1{font-size:34px;font-weight:700;margin:6px 0 4px}
.sub{color:var(--muted);font-size:16px;margin-bottom:24px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:26px}
.kpi{background:var(--surface);border:1px solid var(--border);border-top:2px solid var(--blue);padding:16px 18px}
.kpi .lbl{font-size:13px;font-weight:700;letter-spacing:var(--caps);text-transform:uppercase;color:var(--dim)}
.kpi .val{font-size:40px;font-weight:700;line-height:1.05;margin-top:6px}
.tabs{display:flex;gap:0;border-bottom:1px solid var(--border2);margin-bottom:22px}
.tab{padding:11px 18px;font-size:13px;font-weight:700;letter-spacing:var(--caps);text-transform:uppercase;
color:var(--dim);cursor:pointer;border-bottom:2px solid transparent}
.tab.active{color:var(--fg);border-bottom-color:var(--blue)}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.card{background:var(--surface);border:1px solid var(--border);border-top:2px solid var(--blue);padding:18px}
.card h3{font-size:22px;font-weight:700}
.card .pdesc{color:var(--muted);font-size:14px;margin:4px 0 12px}
.bign{font-size:34px;font-weight:700}.pct{color:var(--blue);font-size:15px;margin-left:6px}
.conf{height:6px;background:var(--elev);margin:10px 0 14px}.conf>span{display:block;height:100%;background:var(--blue)}
.mini{font-size:13px;font-weight:700;letter-spacing:var(--caps);text-transform:uppercase;color:var(--dim);margin:10px 0 5px}
.card ul{list-style:none;font-size:14px;color:var(--fg)}.card li{padding:2px 0 2px 12px;position:relative;color:var(--muted)}
.card li::before{content:'';position:absolute;left:0;top:9px;width:4px;height:4px;background:var(--blue)}
table{width:100%;border-collapse:collapse;font-size:14px}
th{font-size:13px;font-weight:700;letter-spacing:var(--caps);text-transform:uppercase;color:var(--dim);text-align:right;padding:9px 10px;border-bottom:1px solid var(--border2)}
th:first-child,td:first-child{text-align:left}
td{padding:9px 10px;border-bottom:1px dotted var(--border2)}
.statrow{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.bar{height:9px;background:var(--elev);position:relative}.bar>span{display:block;height:100%;background:var(--blue)}
.delta{font-size:14px;font-weight:700}.up{color:var(--green)}.down{color:var(--red)}
.row{display:flex;align-items:center;gap:12px;margin:7px 0}.row .rl{width:150px;color:var(--muted);font-size:14px}
.row .rb{flex:1}.row .rv{width:70px;text-align:right;font-weight:700}
.note{color:var(--dim);font-size:13px;margin-top:18px}
</style></head><body>
<div class="sidebar">
  <div class="logo"><img src="https://transmissionagency.com/wp-content/uploads/2024/05/Logo-Transmission-White.svg" alt="Transmission" style="height:22px;display:block" onerror="this.outerHTML='<div style=&quot;font-weight:700;letter-spacing:.1em&quot;>TRANSMISSION</div>'"></div>
  <div class="seclabel">Models</div>
  <a class="active">Email Nurture Segmentation</a>
</div>
<div class="main">
  <div class="eyebrow">Engagement · email-nurture segmentation</div>
  <h1>Email Nurture Segmentation</h1>
  <div class="sub">Behavioural personas · engagement rates · sequence performance · cohort &amp; policy</div>
  <div class="kpis" id="kpis"></div>
  <div class="tabs" id="tabs"></div>
  <div id="panel"></div>
  <div class="note" id="note"></div>
</div>
<script>
let D=null, TAB='personas';
const TABS=[['personas','Personas'],['rates','Engagement Rates'],['sequence','Sequence Performance'],['cohort','Cohort & Policy']];
function pctw(x){return Math.max(2,Math.round(x*100))}
async function load(){
  const r=await fetch('/api/ease/overview'); D=await r.json();
  const avgO=(D.rates.find(x=>x.metric=='Open rate')||{}).current||0;
  const avgC=(D.rates.find(x=>x.metric=='Click rate')||{}).current||0;
  document.getElementById('kpis').innerHTML=
    kpi('Contacts scored',D.total.toLocaleString())+kpi('Segments',D.personas.length)+
    kpi('Open rate',avgO+'%')+kpi('Click rate',avgC+'%');
  document.getElementById('tabs').innerHTML=TABS.map(t=>`<div class="tab${t[0]==TAB?' active':''}" onclick="setTab('${t[0]}')">${t[1]}</div>`).join('');
  document.getElementById('note').textContent='Score date '+D.score_date+' · trailing 24 months · rules-based v1 on seeded Marketo data (MODEL_DEV.RAW_MKTO).';
  render();
}
function kpi(l,v){return `<div class="kpi"><div class="lbl">${l}</div><div class="val">${v}</div></div>`}
function setTab(t){TAB=t;document.querySelectorAll('.tab').forEach(e=>e.classList.toggle('active',e.textContent==TABS.find(x=>x[0]==t)[1]));render()}
function render(){
  const p=document.getElementById('panel');
  if(TAB=='personas') p.innerHTML='<div class="grid">'+D.personas.map(personaCard).join('')+'</div>';
  else if(TAB=='rates') p.innerHTML=ratesView();
  else if(TAB=='sequence') p.innerHTML=seqView();
  else p.innerHTML=cohortView();
}
function personaCard(s){
  return `<div class="card"><h3>${s.label}</h3><div class="pdesc">${s.desc}</div>
  <div><span class="bign">${s.n.toLocaleString()}</span><span class="pct">${(s.pct*100).toFixed(1)}%</span></div>
  <div class="conf"><span style="width:${pctw(s.confidence)}%"></span></div>
  <div style="font-size:13px;color:var(--dim)">Confidence ${s.confidence} · open ${s.open_rate}% · click ${s.click_rate}% · ${s.recency}d since engage</div>
  <div class="mini">Marketing</div><ul>${s.marketing.map(x=>`<li>${x}</li>`).join('')}</ul>
  <div class="mini">Sales</div><ul>${s.sales.map(x=>`<li>${x}</li>`).join('')}</ul></div>`;
}
function ratesView(){
  return '<div class="statrow">'+D.rates.map(m=>{
    const cls=m.good?'up':'down', sign=m.delta>0?'+':'';
    return `<div class="kpi"><div class="lbl">${m.metric}</div><div class="val">${m.current}%</div>
    <div class="delta ${cls}">${sign}${m.delta} pts</div>
    <div style="font-size:13px;color:var(--dim)">prior ${m.prior}%</div></div>`}).join('')+'</div>'
    +'<div class="note">Current 12 months vs prior 12 months · by email sent date.</div>';
}
function seqView(){
  return `<div class="card" style="border-top-color:var(--blue)"><table><thead><tr>
  <th>Program</th><th>Touched</th><th>Sends</th><th>Open %</th><th>Click %</th><th>Unsub %</th></tr></thead><tbody>`+
  D.sequence.map(s=>`<tr><td>${s.program}</td><td>${s.touched.toLocaleString()}</td><td>${s.sends.toLocaleString()}</td>
  <td>${s.open_rate}</td><td>${s.click_rate}</td><td>${s.unsub_rate}</td></tr>`).join('')+'</tbody></table></div>';
}
function cohortView(){
  const dmax=Math.max(...D.decay.map(d=>d.open_rate));
  const decay='<div class="card"><h3>Send decay</h3><div class="pdesc">Open rate by send number — engagement fades with each send.</div>'+
    D.decay.map(d=>`<div class="row"><div class="rl">Send ${d.send_no}</div><div class="rb bar"><span style="width:${Math.round(d.open_rate/dmax*100)}%"></span></div><div class="rv">${d.open_rate}%</div></div>`).join('')+'</div>';
  const funnel='<div class="card" style="margin-top:14px"><h3>Reactivation funnel (90d)</h3><div class="pdesc">How far contacts get once engaged.</div>'+
    D.funnel.map(f=>`<div class="row"><div class="rl">${f.outcome}</div><div class="rb bar"><span style="width:${pctw(f.pct)}%"></span></div><div class="rv">${(f.pct*100).toFixed(0)}%</div></div>`).join('')+'</div>';
  return decay+funnel;
}
load();
</script></body></html>"""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
