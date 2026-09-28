"""
Generate dashboard.html — interactive WaRF session explorer.
Run:  py warf/plot_dashboard.py
"""
import json
from pathlib import Path
from datetime import datetime, timezone

if __package__ in (None, ""):  # run as `py warf/plot_dashboard.py`, not as a warf.* module
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "warf"
from .engine import A, B, LLR_APPROVE, LLR_REJECT  # noqa: E402
from .paths import sessions_path, html_dir, open_in_browser  # noqa: E402

SESSIONS = sessions_path()
OUTPUT   = html_dir() / "dashboard.html"


def extract(path: Path) -> list[dict]:
    """Read every session in the order it was logged (the file is append-only,
    and this order already matches created_at — verified 2026-09-21). That
    order is also each session's permanent number: stable under every future
    append, so a number quoted in notes or a talk never goes stale, and
    unaffected by whatever domain/decision filter or sort the viewer has set.
    """
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            n = len(rows) + 1   # position among actual sessions, blank lines never counted
            tok_in  = s.get("total_tokens_in",  0) or 0
            tok_out = s.get("total_tokens_out", 0) or 0
            votes   = s.get("votes", [])
            oracle  = s.get("oracle")
            dec     = s.get("decision", "?")
            x_star  = oracle.get("x_star", 0) if oracle else None
            vote_v  = 1 if dec == "APPROVE" else -1
            correct = (vote_v == x_star) if x_star is not None else None
            # When a debate round ran, decision / confidence / sprt_fired are its
            # outcome while votes and sprt_lambda are still Round 1's. The row shows
            # the lambda behind the verdict; the panel replays both rounds.
            debate = s.get("debate") if (s.get("debate") or {}).get("votes") else None
            r1_lambda = round(s.get("sprt_lambda", 0) or 0, 3)
            rows.append({
                "n":            n,
                "id":           s.get("session_id", ""),
                "created_at":   s.get("created_at", ""),
                "artifact":     "/".join(Path(s.get("artifact", "?")).parts[-2:]) if len(Path(s.get("artifact", "?")).parts) >= 2 else Path(s.get("artifact", "?")).name,
                "artifact_full": s.get("artifact", "?"),
                "domain":       s.get("domain", "?"),
                "decision":     dec,
                "confidence":   s.get("confidence", "?"),
                "sprt_lambda":  r1_lambda,
                "verdict_lambda": round(debate.get("sprt_lambda", 0) or 0, 3) if debate else r1_lambda,
                "sprt_fired":   bool(s.get("sprt_fired", False)),
                "agents":       len(votes),
                "tokens":       tok_in + tok_out,
                "oracle":       oracle is not None,
                "correct":      correct,
                "votes": [
                    {
                        "agent":     v.get("agent", "?"),
                        "vote":      v.get("label", "APPROVE" if v.get("vote", 1) == 1 else "REJECT"),
                        "omega":     round(v.get("omega", 0.5), 4),
                        "reasoning": (v.get("reasoning") or ""),
                    }
                    for v in votes
                ],
                "debate": {
                    "sprt_lambda":  round(debate.get("sprt_lambda", 0) or 0, 3),
                    "vote_changes": debate.get("vote_changes") or [],
                    "votes": [
                        {
                            "agent":     v.get("agent", "?"),
                            "vote":      v.get("label", "APPROVE" if v.get("vote", 1) == 1 else "REJECT"),
                            "omega":     round(v.get("omega", 0.5), 4),
                            "changed":   bool(v.get("changed", False)),
                            "reasoning": (v.get("reasoning") or ""),
                        }
                        for v in debate["votes"]
                    ],
                } if debate else None,
            })
    return rows


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>WaRF Session Dashboard</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0f172a;
  color: #e2e8f0;
  font-family: "Segoe UI", system-ui, sans-serif;
  padding: 24px 28px 60px;
  font-size: 13px;
}
h1 { font-size: 1.25rem; font-weight: 600; color: #c8d8f4; margin-bottom: 4px; }
.subtitle { font-size: 0.78rem; color: #64748b; margin-bottom: 20px; }

/* ── Filter bar ─────────────────────────────────────────────────────────── */
.filter-bar {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 16px;
}
.filter-group { display: flex; gap: 4px; align-items: center; }
.filter-label { font-size: 0.7rem; color: #64748b; letter-spacing: 0.08em; text-transform: uppercase; margin-right: 2px; }
.pill {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid #334155;
  background: transparent;
  color: #94a3b8;
  transition: all 0.15s;
}
.pill:hover { border-color: #7ea8d4; color: #c8d8f4; }
.pill.active { background: #1e3a5f; border-color: #4E79A7; color: #c8d8f4; }
.pill.active.approve { background: #052e16; border-color: #22c55e; color: #22c55e; }
.pill.active.reject  { background: #7f1d1d; border-color: #ef4444; color: #ef4444; }
.pill.active.high    { background: #052e16; border-color: #22c55e; color: #22c55e; }
.pill.active.medium  { background: #78350f; border-color: #f59e0b; color: #f59e0b; }
.pill.active.low     { background: #7f1d1d; border-color: #ef4444; color: #ef4444; }

.search-box {
  padding: 4px 10px;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 6px;
  color: #e2e8f0;
  font-size: 0.78rem;
  outline: none;
  width: 200px;
}
.search-box:focus { border-color: #4E79A7; }

/* ── Stats row ──────────────────────────────────────────────────────────── */
.stats-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.stat-chip {
  background: #1e293b;
  border-radius: 8px;
  padding: 8px 14px;
  min-width: 110px;
}
.stat-label { font-size: 0.65rem; color: #64748b; letter-spacing: 0.08em; text-transform: uppercase; }
.stat-value { font-size: 1.25rem; font-weight: 700; color: #c8d8f4; line-height: 1.3; }
.stat-sub   { font-size: 0.65rem; color: #475569; margin-top: 1px; }

/* ── Table ──────────────────────────────────────────────────────────────── */
.table-wrap { overflow-x: auto; border-radius: 10px; border: 1px solid #1e3a5f; }
table { width: 100%; border-collapse: collapse; }
thead th {
  background: #1e293b;
  padding: 8px 10px;
  text-align: left;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7ea8d4;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
thead th:hover { color: #c8d8f4; }
thead th.sorted { color: #e2e8f0; }
thead th .sort-arrow { margin-left: 4px; opacity: 0.5; }
thead th.sorted .sort-arrow { opacity: 1; }
tbody tr {
  border-top: 1px solid #1e3a5f;
  cursor: pointer;
  transition: background 0.1s;
}
tbody tr:hover { background: #1e293b; }
tbody tr.expanded { background: #1e293b; }
tbody td { padding: 7px 10px; vertical-align: middle; white-space: nowrap; }
.num-col { font-variant-numeric: tabular-nums; width: 1%; }
.detail-row td { padding: 0; background: #0f172a; cursor: default; }
.detail-row:hover { background: #0f172a !important; }

/* ── Badges ─────────────────────────────────────────────────────────────── */
.badge {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
}
.badge.approve { background: #052e16; color: #22c55e; }
.badge.reject  { background: #7f1d1d; color: #ef4444; }
.badge.high    { background: #052e16; color: #22c55e; }
.badge.medium  { background: #78350f; color: #f59e0b; }
.badge.low     { background: #7f1d1d; color: #ef4444; }
.badge.logic   { background: #1e3a5f; color: #7ea8d4; }
.badge.security   { background: #450a0a; color: #fca5a5; }
.badge.performance { background: #431407; color: #fdba74; }

.lambda-val { font-family: monospace; font-size: 0.78rem; }
.lambda-pos { color: #22c55e; }
.lambda-neg { color: #ef4444; }

.muted { color: #475569; }
.oracle-correct { color: #22c55e; }
.oracle-wrong   { color: #ef4444; }

/* ── Detail panel ───────────────────────────────────────────────────────── */
.detail-panel {
  padding: 14px 16px;
  background: #0f172a;
  border-top: 1px solid #1e3a5f;
}
.detail-artifact {
  font-size: 0.72rem;
  color: #64748b;
  margin-bottom: 10px;
  font-family: monospace;
}
.vote-table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
.vote-table th {
  font-size: 0.65rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #475569;
  padding: 4px 8px;
  text-align: left;
  border-bottom: 1px solid #1e3a5f;
}
.vote-table td { padding: 6px 8px; border-bottom: 1px solid #1e293b; vertical-align: top; }
.reasoning {
  font-size: 0.72rem;
  color: #94a3b8;
  line-height: 1.5;
  max-width: 520px;
  white-space: normal;
}
.reasoning-clip { cursor: pointer; }
.reasoning-clip:hover { color: #c8d8f4; }
.expand-hint { color: #4E79A7; font-size: 0.68rem; margin-left: 4px; white-space: nowrap; }

/* ── Reasoning modal ─────────────────────────────────────────────────── */
#r-modal { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.78); z-index:9999; align-items:center; justify-content:center; }
#r-modal.open { display:flex; }
.r-modal-box { background:#1e293b; border:1px solid #334155; border-radius:8px; max-width:680px; width:90%; max-height:80vh; display:flex; flex-direction:column; }
.r-modal-head { padding:12px 16px; border-bottom:1px solid #334155; display:flex; justify-content:space-between; align-items:center; flex-shrink:0; }
.r-modal-agent { font-size:0.82rem; font-weight:700; color:#e2e8f0; }
.r-modal-close { background:none; border:none; color:#94a3b8; cursor:pointer; font-size:1.2rem; line-height:1; padding:0; }
.r-modal-close:hover { color:#e2e8f0; }
.r-modal-body { padding:16px; overflow-y:auto; font-size:0.78rem; color:#94a3b8; line-height:1.7; white-space:pre-wrap; word-break:break-word; }

.empty-msg { text-align: center; color: #475569; padding: 32px; font-size: 0.82rem; }
.subtitle b { color: #94a3b8; }
.threshold-row td {
  padding: 5px 8px;
  font-size: 0.68rem;
  font-style: italic;
  color: #64748b;
  border-bottom: 1px solid #1e293b;
}
.threshold-row td .thresh-check { color: #22c55e; font-weight: 700; font-style: normal; }

/* ── Debate sessions: two rounds in one panel ────────────────────────── */
.round-head {
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #c8d8f4;
  font-weight: 700;
  margin: 14px 0 4px;
}
.round-head:first-of-type { margin-top: 2px; }
.round-head .round-sub { color: #64748b; font-weight: 400; text-transform: none; letter-spacing: 0; margin-left: 6px; }
.round-note { font-size: 0.72rem; color: #94a3b8; margin: 2px 0 6px; }
.round-note b { color: #e2e8f0; }
.changed-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #0f172a;
  background: #f59e0b;
  vertical-align: middle;
}
.debate-tag { color: #f59e0b; font-size: 0.7rem; font-weight: 700; }
.debate-summary {
  font-size: 0.8rem;
  color: #e2e8f0;
  background: #1e293b;
  border-left: 3px solid #f59e0b;
  border-radius: 0 4px 4px 0;
  padding: 7px 12px;
  margin: 2px 0 12px;
}
.debate-summary b { color: #fbbf24; }
.detail-panel.debate .reasoning { max-width: 900px; }
.detail-panel.debate .vote-table td { padding-top: 4px; padding-bottom: 4px; }
</style>
</head>
<body>

<h1>WaRF Session Dashboard</h1>
<div class="subtitle">Click a row to expand agent votes &middot; Click column headers to sort &nbsp;&nbsp;&mdash;&nbsp;&nbsp; θ: <b>LOGIC</b> 0.0 &nbsp;<b>SECURITY</b> +0.2 (reject-biased) &nbsp;<b>PERF</b> &minus;0.1 &nbsp;&middot;&nbsp; APPROVE if weighted score &ge; θ</div>

<div class="filter-bar">
  <div class="filter-group">
    <span class="filter-label">Domain</span>
    <button class="pill active" data-filter="domain" data-value="">All</button>
    <button class="pill" data-filter="domain" data-value="LOGIC">Logic</button>
    <button class="pill" data-filter="domain" data-value="SECURITY">Security</button>
    <button class="pill" data-filter="domain" data-value="PERFORMANCE">Perf</button>
  </div>
  <div class="filter-group">
    <span class="filter-label">Decision</span>
    <button class="pill active" data-filter="decision" data-value="">All</button>
    <button class="pill approve" data-filter="decision" data-value="APPROVE">Approve</button>
    <button class="pill reject"  data-filter="decision" data-value="REJECT">Reject</button>
  </div>
  <div class="filter-group">
    <span class="filter-label">Confidence</span>
    <button class="pill active" data-filter="confidence" data-value="">All</button>
    <button class="pill high"   data-filter="confidence" data-value="HIGH">High</button>
    <button class="pill medium" data-filter="confidence" data-value="MEDIUM">Medium</button>
    <button class="pill low"    data-filter="confidence" data-value="LOW">Low</button>
  </div>
  <div class="filter-group">
    <span class="filter-label">Oracle</span>
    <button class="pill active" data-filter="oracle" data-value="">All</button>
    <button class="pill" data-filter="oracle" data-value="true">Labelled</button>
    <button class="pill" data-filter="oracle" data-value="false">Unlabelled</button>
  </div>
  <div class="filter-group">
    <input class="search-box" id="search" placeholder="Search artifact, or #47 for a session…" />
  </div>
</div>

<div class="stats-row" id="stats"></div>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th data-col="n" title="Session number — stable, in the order each review was logged">#<span class="sort-arrow"></span></th>
        <th data-col="created_at">Date <span class="sort-arrow">↓</span></th>
        <th data-col="artifact">Artifact <span class="sort-arrow"></span></th>
        <th data-col="domain">Domain <span class="sort-arrow"></span></th>
        <th data-col="decision">Decision <span class="sort-arrow"></span></th>
        <th data-col="confidence">Confidence <span class="sort-arrow"></span></th>
        <th data-col="verdict_lambda">λ <span class="sort-arrow"></span></th>
        <th data-col="agents">Agents <span class="sort-arrow"></span></th>
        <th data-col="tokens">Tokens <span class="sort-arrow"></span></th>
        <th data-col="oracle">Oracle <span class="sort-arrow"></span></th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<script>
const DATA = __DATA__;

const AGENT_COLOR = {
  AUDITOR:       "#4E79A7",
  ADVOCATE:      "#59A14F",
  SKEPTIC:       "#E15759",
  BOUNDARY:      "#F28E2B",
  "TEST-FOCUSED":"#B07AA1",
};

let filters = { domain: "", decision: "", confidence: "", oracle: "", search: "" };
let sortCol = "created_at";
let sortDir = -1;
let expandedId = null;

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toISOString().slice(0, 10) + " " + d.toISOString().slice(11, 16);
}

function applyFilters() {
  // "#47" (a leading # followed only by digits) jumps to that exact session
  // number instead of the usual filename substring match — a session number
  // quoted in notes or a talk is typed here verbatim. It overrides the pill
  // filters too, so a stale Domain/Decision pill from an earlier demo can
  // never hide the one row a number search is meant to guarantee.
  const numMatch = filters.search.trim().match(/^#(\d+)$/);
  if (numMatch) return DATA.filter(r => r.n === Number(numMatch[1]));
  return DATA.filter(r => {
    if (filters.domain     && r.domain     !== filters.domain)              return false;
    if (filters.decision   && r.decision   !== filters.decision)            return false;
    if (filters.confidence && r.confidence !== filters.confidence)          return false;
    if (filters.oracle !== "" && String(r.oracle) !== filters.oracle)       return false;
    if (filters.search && !r.artifact_full.toLowerCase().includes(filters.search.toLowerCase())) return false;
    return true;
  });
}

function sorted(rows) {
  return [...rows].sort((a, b) => {
    const va = a[sortCol] ?? "", vb = b[sortCol] ?? "";
    if (typeof va === "string") return sortDir * va.localeCompare(vb);
    return sortDir * (va - vb);
  });
}

function updateStats(rows) {
  const total      = rows.length;
  const rejects    = rows.filter(r => r.decision === "REJECT").length;
  const early      = rows.filter(r => r.sprt_fired).length;
  const withTok    = rows.filter(r => r.tokens > 0);
  const avgTok     = withTok.length ? Math.round(withTok.reduce((s,r) => s+r.tokens, 0) / withTok.length) : 0;
  const labelled   = rows.filter(r => r.oracle).length;
  const avgAgents  = total ? (rows.reduce((s,r) => s + r.agents, 0) / total).toFixed(1) : "—";

  const el = document.getElementById("stats");
  el.innerHTML = "";
  [
    { label: "Sessions",       value: total,                                              sub: "matching filters" },
    { label: "REJECT",         value: total ? `${Math.round(rejects/total*100)}%` : "—", sub: `${rejects} of ${total}` },
    { label: "SPRT early",     value: total ? `${Math.round(early/total*100)}%` : "—",   sub: `${early} fired early` },
    { label: "Avg reviewers",  value: total ? `${avgAgents} / 5` : "—",                  sub: "mean pool depth" },
    { label: "Avg tokens",     value: avgTok > 0 ? avgTok.toLocaleString() : "—",        sub: withTok.length ? `${withTok.length} with data` : "no token data" },
    { label: "Oracle labels",  value: labelled,                                           sub: `${total - labelled} unlabelled` },
  ].forEach(c => {
    const d = document.createElement("div");
    d.className = "stat-chip";
    d.innerHTML = `<div class="stat-label">${c.label}</div><div class="stat-value">${c.value}</div><div class="stat-sub">${c.sub}</div>`;
    el.appendChild(d);
  });
}

function domainClass(d)     { return d.toLowerCase(); }
function confClass(c)       { return c.toLowerCase(); }
function decClass(d)        { return d.toLowerCase(); }

// One round of votes as table rows, with lambda replayed from zero. Used once for
// an ordinary session and twice for a debate session (Round 2 restarts at 0 with
// the weights frozen, exactly as the engine does).
function renderRound(votes, skippedText, clip = 350) {
  // The engine's own constants, injected by main(). The step is asymmetric: an
  // APPROVE moves lambda by omega * log(P1/P0), a REJECT by omega * log((1-P1)/(1-P0)).
  const SPRT_A      = __SPRT_A__;
  const SPRT_B      = __SPRT_B__;
  const LLR_APPROVE = __LLR_APPROVE__;
  const LLR_REJECT  = __LLR_REJECT__;

  let runL = 0;
  let threshIdx = -1;

  const computed = votes.map((v, i) => {
    const omega = Math.max(0.001, Math.min(0.999, v.omega));
    const delta = omega * (v.vote === "APPROVE" ? LLR_APPROVE : LLR_REJECT);
    runL += delta;
    const crossed = threshIdx < 0 && (runL <= SPRT_B || runL >= SPRT_A);
    if (crossed) threshIdx = i;
    return { ...v, delta, runL, crossed };
  });

  const vrows = computed.map(v => {
    const col   = AGENT_COLOR[v.agent] || "#94a3b8";
    const dec   = v.vote === "APPROVE" ? `<span class="badge approve">APPROVE</span>` : `<span class="badge reject">REJECT</span>`;
    const rFull = v.reasoning ? v.reasoning.replace(/</g,"&lt;").replace(/>/g,"&gt;") : "";
    const rIdx  = _R.length;
    if (v.reasoning) _R.push({ agent: v.agent, text: v.reasoning });
    const r = v.reasoning
      ? (v.reasoning.length > clip
          ? `<div class="reasoning reasoning-clip" onclick="showReasoning(${rIdx})">${rFull.slice(0,clip)}… <span class="expand-hint">↗ expand</span></div>`
          : `<div class="reasoning">${rFull}</div>`)
      : `<span class="muted">—</span>`;
    const dSign = v.delta >= 0 ? "+" : "";
    const lSign = v.runL  >= 0 ? "+" : "";
    const dCls  = v.delta >= 0 ? "lambda-pos" : "lambda-neg";
    const lCls  = v.runL  >= 0 ? "lambda-pos" : "lambda-neg";

    const chg = v.changed ? `<span class="changed-tag">changed</span>` : "";

    const mainRow = `<tr>
      <td style="color:${col};font-weight:600;white-space:nowrap">${v.agent}</td>
      <td>${dec}${chg}</td>
      <td class="muted" style="font-family:monospace">${v.omega.toFixed(4)}</td>
      <td><span class="lambda-val ${dCls}">${dSign}${v.delta.toFixed(3)}</span></td>
      <td><span class="lambda-val ${lCls}">${lSign}${v.runL.toFixed(3)}</span></td>
      <td>${r}</td>
    </tr>`;

    const crossRow = v.crossed
      ? `<tr class="threshold-row"><td colspan="6"><span class="thresh-check">✓ Threshold crossed</span> &mdash; ${skippedText}</td></tr>`
      : "";

    return mainRow + crossRow;
  }).join("");

  return { vrows, lastL: runL, crossed: threshIdx >= 0 };
}

function buildDetail(row) {
  if (!row.votes.length) return `<div class="detail-panel"><span class="muted">No votes recorded.</span></div>`;

  // A debate panel holds two tables; shorter reasoning excerpts keep both on one screen.
  const clip = row.debate ? 230 : 350;
  const r1 = renderRound(row.votes, "remaining agents skipped", clip);
  const vrows = r1.vrows;

  const oracleNote = row.oracle && row.correct !== null
    ? `<div style="margin-top:8px;font-size:0.72rem">Oracle: <span class="${row.correct ? 'oracle-correct' : 'oracle-wrong'}">${row.correct ? "✓ Correct" : "✗ Wrong"}</span></div>`
    : "";

  if (!row.debate) {
    return `<div class="detail-panel">
    <div class="detail-artifact">${row.artifact_full}</div>
    <table class="vote-table">
      <thead><tr><th>Agent</th><th>Vote</th><th>ω</th><th>Δλ</th><th>Running λ</th><th>Reasoning</th></tr></thead>
      <tbody>${vrows}</tbody>
    </table>
    ${oracleNote}
  </div>`;
  }

  // Debate session: the row's decision, confidence and lambda are Round 2's.
  const r2      = renderRound(row.debate.votes, "remaining agents not asked again", clip);
  const fmt     = x => (x >= 0 ? "+" : "") + x.toFixed(3);
  const head    = `<thead><tr><th>Agent</th><th>Vote</th><th>ω</th><th>Δλ</th><th>Running λ</th><th>Reasoning</th></tr></thead>`;
  const movers  = row.debate.votes.filter(v => v.changed).map(v => v.agent);
  const r1Note  = r1.crossed
    ? `A debate round followed.`
    : `No boundary crossed (λ = ${fmt(r1.lastL)}) &rarr; debate. λ restarts at 0; the weights stay frozen.`;
  const chgNote = movers.length
    ? `<b>${movers.length} of ${row.debate.votes.length}</b> changed their vote: <b>${movers.join(", ")}</b>.`
    : `Nobody changed their vote.`;
  // The whole story in one line, so it is on screen before anyone scrolls.
  const summary = `<div class="debate-summary"><span class="debate-tag">DEBATE</span>&nbsp; Round 1 ended without a boundary crossing (λ = ${fmt(r1.lastL)}). Round 2: `
    + (movers.length ? `<b>${movers.length} of ${row.debate.votes.length} changed their vote</b> (${movers.join(", ")})` : `nobody changed their vote`)
    + ` &rarr; <b>${row.decision} [${row.confidence}]</b>, λ = ${fmt(r2.lastL)}.</div>`;

  return `<div class="detail-panel debate">
    <div class="detail-artifact">${row.artifact_full}</div>
    ${summary}
    <div class="round-head">Round 1<span class="round-sub">independent votes</span></div>
    <table class="vote-table">${head}<tbody>${r1.vrows}</tbody></table>
    <div class="round-note">${r1Note}</div>
    <div class="round-head">Round 2 &mdash; debate<span class="round-sub">each agent has read the others' Round-1 reasoning</span></div>
    <table class="vote-table">${head}<tbody>${r2.vrows}</tbody></table>
    <div class="round-note">${chgNote} The verdict in the row above comes from this round (λ = ${fmt(r2.lastL)}).</div>
    ${oracleNote}
  </div>`;
}

function render() {
  _R = [];
  const rows = sorted(applyFilters());
  updateStats(rows);

  const tbody = document.getElementById("tbody");
  tbody.innerHTML = "";

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty-msg">No sessions match the current filters.</td></tr>`;
    return;
  }

  rows.forEach(row => {
    // The lambda behind the verdict: Round 2's when a debate ran, else Round 1's.
    const lClass = row.verdict_lambda >= 0 ? "lambda-pos" : "lambda-neg";
    const sign   = row.verdict_lambda >= 0 ? "+" : "";
    const debTag = row.debate ? ` +${row.debate.votes.length} <span class="debate-tag">DEBATE</span>` : "";
    const oCell  = row.oracle
      ? (row.correct === true  ? `<span class="oracle-correct">✓</span>`
       : row.correct === false ? `<span class="oracle-wrong">✗</span>`
       : `<span class="muted">labelled</span>`)
      : `<span class="muted">—</span>`;

    const tr = document.createElement("tr");
    tr.dataset.id = row.id;
    tr.id = "s" + row.n;
    if (expandedId === row.id) tr.classList.add("expanded");
    tr.innerHTML = `
      <td class="muted num-col">#${row.n}</td>
      <td class="muted">${fmtDate(row.created_at)}</td>
      <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis">${row.artifact}</td>
      <td><span class="badge ${domainClass(row.domain)}">${row.domain}</span></td>
      <td><span class="badge ${decClass(row.decision)}">${row.decision}</span></td>
      <td><span class="badge ${confClass(row.confidence)}">${row.confidence}</span></td>
      <td><span class="lambda-val ${lClass}">${sign}${row.verdict_lambda.toFixed(3)}</span></td>
      <td>${row.agents}/5${debTag}${row.sprt_fired ? ' <span style="color:#4E79A7;font-size:0.7rem">SPRT</span>' : ""}</td>
      <td>${row.tokens > 0 ? row.tokens.toLocaleString() : '<span class="muted">—</span>'}</td>
      <td>${oCell}</td>`;

    tr.addEventListener("click", () => {
      const next = expandedId === row.id ? null : row.id;
      expandedId = next;
      render();
    });

    tbody.appendChild(tr);

    if (expandedId === row.id) {
      const dr = document.createElement("tr");
      dr.className = "detail-row";
      const td = document.createElement("td");
      td.colSpan = 10;
      td.innerHTML = buildDetail(row);
      dr.appendChild(td);
      tbody.appendChild(dr);
    }
  });
}

// ── Pill filters ──────────────────────────────────────────────────────────────
document.querySelectorAll(".pill[data-filter]").forEach(btn => {
  btn.addEventListener("click", () => {
    const f = btn.dataset.filter;
    filters[f] = btn.dataset.value;
    document.querySelectorAll(`.pill[data-filter="${f}"]`).forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    expandedId = null;
    render();
  });
});

// ── Search ────────────────────────────────────────────────────────────────────
document.getElementById("search").addEventListener("input", e => {
  filters.search = e.target.value;
  // Typing "#47" both finds and opens that session — one action, not two.
  const numMatch = filters.search.trim().match(/^#(\d+)$/);
  const hit = numMatch ? DATA.find(r => r.n === Number(numMatch[1])) : null;
  expandedId = hit ? hit.id : null;
  render();
  if (hit) document.getElementById("s" + hit.n)?.scrollIntoView({ block: "center" });
});

// ── Sort ──────────────────────────────────────────────────────────────────────
document.querySelectorAll("thead th[data-col]").forEach(th => {
  th.addEventListener("click", () => {
    const col = th.dataset.col;
    if (sortCol === col) sortDir *= -1; else { sortCol = col; sortDir = -1; }
    document.querySelectorAll("thead th").forEach(h => {
      h.classList.remove("sorted");
      const arr = h.querySelector(".sort-arrow");
      if (arr) arr.textContent = "";
    });
    th.classList.add("sorted");
    const arr = th.querySelector(".sort-arrow");
    if (arr) arr.textContent = sortDir === -1 ? "↓" : "↑";
    render();
  });
});

let _R = [];

function showReasoning(i) {
  const item = _R[i];
  if (!item) return;
  document.getElementById("r-modal-agent").textContent = item.agent + " — Full Reasoning";
  document.getElementById("r-modal-body").textContent = item.text;
  document.getElementById("r-modal").classList.add("open");
}
function closeReasoning() {
  document.getElementById("r-modal").classList.remove("open");
}
document.addEventListener("keydown", e => { if (e.key === "Escape") closeReasoning(); });

render();
</script>

<div id="r-modal" onclick="if(event.target===this)closeReasoning()">
  <div class="r-modal-box">
    <div class="r-modal-head">
      <span id="r-modal-agent" class="r-modal-agent"></span>
      <button class="r-modal-close" onclick="closeReasoning()">&#x2715;</button>
    </div>
    <div id="r-modal-body" class="r-modal-body"></div>
  </div>
</div>

</body>
</html>
"""


def main() -> None:
    rows = extract(SESSIONS)
    if not rows:
        print("No sessions found.")
        return
    print(f"Sessions: {len(rows)}  oracle-labelled: {sum(1 for r in rows if r['oracle'])}")
    # The detail panel replays each session's lambda in the browser. Its constants
    # come from the engine so the replay cannot drift from what was logged. They go
    # in before the data, so a token quoted in some agent's reasoning stays text.
    html = _TEMPLATE
    for token, value in (("__SPRT_A__", A), ("__SPRT_B__", B),
                         ("__LLR_APPROVE__", LLR_APPROVE), ("__LLR_REJECT__", LLR_REJECT)):
        html = html.replace(token, repr(float(value)))
    html = html.replace("__DATA__", json.dumps(rows).replace("</script>", r"<\/script>"))
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Written: {OUTPUT}")
    open_in_browser(OUTPUT)


if __name__ == "__main__":
    main()
