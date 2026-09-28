"""
Generate why_not_two_agents.html — pool-size vs SPRT-boundary analysis.
Run:  py warf/plot_slide13.py
"""
import json
from pathlib import Path

if __package__ in (None, ""):  # run as `py warf/plot_slide13.py`, not as a warf.* module
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "warf"
from .engine import (  # noqa: E402  — the engine's constants, not copies of them
    A as SPRT_A, B as SPRT_B, ALPHA_ERR as ALPHA, BETA_ERR as BETA,
    LLR_APPROVE, LLR_REJECT,
)
from .paths import sessions_path, html_dir  # noqa: E402

SESSIONS = sessions_path()
OUTPUT   = html_dir() / "why_not_two_agents.html"

LLR_ABS_REJ = abs(LLR_REJECT)    # ≈ 1.253  used for REJECT-direction max-Λ
LLR_ABS_APP = LLR_APPROVE        # ≈ 0.981  used for APPROVE-direction max-Λ

AGENT_ORDER = ["AUDITOR", "ADVOCATE", "SKEPTIC", "BOUNDARY", "TEST-FOCUSED"]
AGENT_COLOR = {
    "AUDITOR":      "#4E79A7",
    "ADVOCATE":     "#F28E2B",
    "SKEPTIC":      "#E15759",
    "BOUNDARY":     "#59A14F",
    "TEST-FOCUSED": "#B07AA1",
}


def _latest_omegas(path: Path) -> tuple[dict, str, str]:
    """Each agent's ω after its most recent label, within ONE domain.

    Weights are per domain, so the page must not add up ω from different ones.
    The domain is that of the most recent labelled session; it and the date of
    its newest label are returned for the provenance line — the talk's demo and
    notes quote LOGIC, and a page of unnamed "current weights" invites a
    comparison across domains.  Returns (omegas, domain, date); ({}, "", "")
    when nothing is labelled yet.
    """
    labelled = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            if s.get("oracle") and s["oracle"].get("weight_updates"):
                labelled.append(s)
    if not labelled:
        return {}, "", ""
    domain = labelled[-1].get("domain", "")
    latest, newest = {}, ""
    for s in labelled:
        if s.get("domain") != domain:
            continue
        newest = max(newest, s.get("created_at", "")[:10])
        for wu in s["oracle"]["weight_updates"]:
            latest[wu["agent"]] = wu["omega_after"]
    return latest, domain, newest


def _early_stop_rate(path: Path) -> dict:
    """Sessions that ended at an SPRT boundary, i.e. with HIGH confidence.

    Only the log's own `sprt_fired` flag counts.  The old test also counted any
    session with fewer than five votes, which swept in every two- and
    three-agent pool that ran out of agents at LOW or MEDIUM: 178 of 248 (72%)
    on the talk corpus, under a label that said "HIGH confidence", where the
    log has 111 (45%) — the dashboard's number.  The pool size is not logged,
    so the figure is stated for all sessions, not for "5-agent sessions".
    """
    early = total = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            if not s.get("votes"):
                continue
            total += 1
            if s.get("sprt_fired"):
                early += 1
    pct = round(early / total * 100) if total else 0
    return {"early": early, "total": total, "pct": pct}


def page_figures(path: Path | None = None) -> dict:
    """The numbers the page shows, for any report that wants to quote them."""
    path = path or SESSIONS
    omegas_raw, domain, newest = _latest_omegas(path)
    # Fill any missing agents with prior mean (α=1,β=1 → ω=0.5)
    omegas = {a: omegas_raw.get(a, 0.5) for a in AGENT_ORDER}
    sorted_agents = sorted(AGENT_ORDER, key=lambda a: omegas[a], reverse=True)
    sorted_omegas = [omegas[a] for a in sorted_agents]
    pool_sizes = [2, 3, 4, 5]
    return {
        "omegas": omegas,
        "sorted_agents": sorted_agents,
        "domain": domain,
        "newest_label": newest,
        "pool_sizes": pool_sizes,
        "max_rej": {n: sum(sorted_omegas[:n]) * LLR_ABS_REJ for n in pool_sizes},
        "max_app": {n: sum(sorted_omegas[:n]) * LLR_ABS_APP for n in pool_sizes},
        "early": _early_stop_rate(path),
    }


def main() -> None:
    fig = page_figures(SESSIONS)
    omegas, sorted_agents, pool_sizes = fig["omegas"], fig["sorted_agents"], fig["pool_sizes"]
    max_lambda_rej, max_lambda_app, es = fig["max_rej"], fig["max_app"], fig["early"]
    if fig["domain"]:
        weights_scope = (f"{fig['domain']} domain — ω after each agent's most recent label "
                         f"(newest {fig['newest_label']}); weights are per domain")
    else:
        weights_scope = "no labelled sessions yet — every agent at the prior ω = 0.5"

    agents_json = json.dumps([
        {"name": a, "omega": round(omegas[a], 4), "color": AGENT_COLOR[a]}
        for a in sorted_agents
    ])
    pool_json = json.dumps([
        {
            "n": n,
            "rej": round(max_lambda_rej[n], 3),
            "app": round(max_lambda_app[n], 3),
            "agents": sorted_agents[:n],
        }
        for n in pool_sizes
    ])

    html = _TEMPLATE.format(
        sprt_a=round(SPRT_A, 3),
        sprt_b_abs=round(abs(SPRT_B), 3),
        llr_rej=round(LLR_ABS_REJ, 3),
        llr_app=round(LLR_ABS_APP, 3),
        agents_json=agents_json,
        pool_json=pool_json,
        es_pct=es["pct"],
        es_early=es["early"],
        es_total=es["total"],
        weights_scope=weights_scope,
    )

    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Written: {OUTPUT}")
    for n in pool_sizes:
        rej = max_lambda_rej[n]
        app = max_lambda_app[n]
        can = "REJECT" if rej >= abs(SPRT_B) else ""
        can += "+APPROVE" if app >= SPRT_A else ""
        print(f"  n={n}: max-Λ(rej)={rej:.3f}  max-Λ(app)={app:.3f}  can reach: {can or 'neither'}")


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>WaRF — Pool Size vs SPRT Boundaries</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #0f172a;
  color: #e2e8f0;
  font-family: "Segoe UI", system-ui, sans-serif;
  padding: 28px 32px 60px;
  font-size: 13px;
}}
h1 {{ font-size: 1.3rem; font-weight: 600; color: #c8d8f4; margin-bottom: 4px; }}
.subtitle {{ font-size: 0.80rem; color: #64748b; margin-bottom: 6px; line-height: 1.6; }}
.provenance {{
  font-size: 0.70rem; color: #334155; background: #1e293b;
  border-left: 3px solid #334155; padding: 6px 12px;
  margin-bottom: 24px; border-radius: 0 4px 4px 0;
  font-family: "Consolas", monospace;
}}
.layout {{ display: flex; gap: 28px; flex-wrap: wrap; align-items: flex-start; }}
.chart-card {{
  background: #1e293b; border-radius: 10px; padding: 16px 18px 14px;
  flex: 1 1 420px;
}}
.card-title {{
  font-size: 0.75rem; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: #7ea8d4; margin-bottom: 10px;
}}
canvas {{ display: block; width: 100%; }}
.side {{ flex: 0 0 240px; display: flex; flex-direction: column; gap: 14px; }}
.agent-table {{ width: 100%; border-collapse: collapse; }}
.agent-table th {{
  font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: #475569;
  padding: 4px 8px; text-align: left; border-bottom: 1px solid #1e3a5f;
}}
.agent-table td {{ padding: 5px 8px; font-size: 0.78rem; vertical-align: middle; }}
.omega-bar-bg {{ background: #0f172a; border-radius: 3px; height: 6px; width: 100px; }}
.omega-bar    {{ height: 6px; border-radius: 3px; }}
.dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }}
.stat-box {{
  background: #1e293b; border-radius: 10px; padding: 14px 16px;
}}
.stat-val {{ font-size: 2rem; font-weight: 700; color: #22c55e; line-height: 1; }}
.stat-lbl {{ font-size: 0.72rem; color: #64748b; margin-top: 4px; line-height: 1.5; }}
.formula-box {{
  background: #1e293b; border-radius: 10px; padding: 14px 16px;
  font-family: "Consolas", monospace; font-size: 0.78rem; color: #94a3b8;
  line-height: 1.9;
}}
.formula-box b {{ color: #c8d8f4; }}
.hl {{ color: #f59e0b; }}
#tooltip {{
  position: fixed; background: #0f172a; border: 1px solid #334155;
  border-radius: 6px; padding: 7px 11px; font-size: 0.76rem;
  pointer-events: none; display: none; z-index: 999; line-height: 1.6; color: #e2e8f0;
}}
</style>
</head>
<body>
<h1>Why Not Two Well-Calibrated Agents?</h1>
<div class="subtitle">
  Maximum achievable |Λ| by pool size, versus SPRT early-stop boundaries.<br>
  A pool can fire early only when its max-Λ reaches the relevant boundary.
</div>
<div class="provenance">
  Weights: {weights_scope}<br>
  Boundaries fixed by α={alpha}, β={beta} &nbsp;·&nbsp; SPRT_B ≈ {sprt_b_abs_neg}, SPRT_A ≈ +{sprt_a}
</div>

<div class="layout">
  <div class="chart-card">
    <div class="card-title">Max-Λ by pool size vs SPRT boundaries</div>
    <canvas id="chart" height="300"></canvas>
  </div>
  <div class="side">
    <div class="chart-card">
      <div class="card-title">Current agent weights (ω)</div>
      <table class="agent-table">
        <thead><tr><th>Agent</th><th>ω</th><th></th></tr></thead>
        <tbody id="agent-rows"></tbody>
      </table>
    </div>
    <div class="stat-box">
      <div class="stat-val" id="es-pct">{es_pct}%</div>
      <div class="stat-lbl">of all logged sessions ended at an SPRT boundary &#x2014; <strong>HIGH</strong> confidence<br>
        <span style="color:#475569">({es_early} of {es_total} sessions, pools of every size)</span><br>
        Structurally impossible with n=2.
      </div>
    </div>
    <div class="formula-box">
      <b>|Λ|<sub>max</sub>(n)</b> = (Σ ω<sub>i</sub>) × LLR<br>
      <span class="hl">REJECT</span>: LLR = {llr_rej} → need {sprt_b_abs}<br>
      <span class="hl">APPROVE</span>: LLR = {llr_app} → need {sprt_a}
    </div>
  </div>
</div>
<div id="tooltip"></div>

<script>
const AGENTS   = {agents_json};
const POOLS    = {pool_json};
const SPRT_A   = {sprt_a};
const SPRT_B_ABS = {sprt_b_abs};
const LLR_REJ  = {llr_rej};
const LLR_APP  = {llr_app};
const AGENT_COLOR = {{}};
AGENTS.forEach(a => AGENT_COLOR[a.name] = a.color);

// Agent table
const tbody = document.getElementById("agent-rows");
AGENTS.forEach((a, i) => {{
  const pct = Math.round(a.omega * 100);
  const inPool = i < 2 ? " (top-2)" : i < 3 ? " (top-3)" : "";
  tbody.innerHTML += `<tr>
    <td><span class="dot" style="background:${{a.color}}"></span>${{a.name}}</td>
    <td>${{a.omega.toFixed(3)}}</td>
    <td><div class="omega-bar-bg"><div class="omega-bar" style="width:${{pct}}px;background:${{a.color}}"></div></div></td>
  </tr>`;
}});

// Chart
(function() {{
  const canvas = document.getElementById("chart");
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.offsetWidth || 420;
  const H = 300;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const PAD = {{l: 52, r: 20, t: 24, b: 56}};
  const pw = W - PAD.l - PAD.r;
  const ph = H - PAD.t - PAD.b;
  const maxY = 3.4;
  const yS = v => PAD.t + (1 - v / maxY) * ph;
  const cx = i => PAD.l + (pw / POOLS.length) * i + (pw / POOLS.length) / 2;
  const bw = Math.min(55, (pw / POOLS.length) * 0.45);

  ctx.fillStyle = "#1e293b";
  ctx.fillRect(0, 0, W, H);

  // Grid
  [0, 1, 2, 3].forEach(v => {{
    const py = yS(v);
    ctx.strokeStyle = "#1e3a5f"; ctx.lineWidth = 0.7;
    ctx.beginPath(); ctx.moveTo(PAD.l, py); ctx.lineTo(PAD.l + pw, py); ctx.stroke();
    ctx.fillStyle = "#475569"; ctx.font = "10px monospace"; ctx.textAlign = "right";
    ctx.fillText(v.toFixed(0), PAD.l - 5, py + 3.5);
  }});

  // REJECT boundary line
  const yB = yS(SPRT_B_ABS);
  ctx.strokeStyle = "#ef4444"; ctx.lineWidth = 1.4;
  ctx.setLineDash([6, 4]);
  ctx.beginPath(); ctx.moveTo(PAD.l, yB); ctx.lineTo(PAD.l + pw, yB); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#ef4444"; ctx.font = "bold 10px sans-serif"; ctx.textAlign = "left";
  ctx.fillText(`|λ_B| = ${{SPRT_B_ABS}} (REJECT boundary)`, PAD.l + 4, yB - 4);

  // APPROVE boundary line
  const yA = yS(SPRT_A);
  ctx.strokeStyle = "#22c55e"; ctx.lineWidth = 1.4;
  ctx.setLineDash([6, 4]);
  ctx.beginPath(); ctx.moveTo(PAD.l, yA); ctx.lineTo(PAD.l + pw, yA); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#22c55e"; ctx.font = "bold 10px sans-serif"; ctx.textAlign = "left";
  ctx.fillText(`λ_A = ${{SPRT_A}} (APPROVE boundary)`, PAD.l + 4, yA - 4);

  // Axes
  ctx.strokeStyle = "#334155"; ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(PAD.l, PAD.t); ctx.lineTo(PAD.l, PAD.t + ph);
  ctx.lineTo(PAD.l + pw, PAD.t + ph); ctx.stroke();

  const tooltip = document.getElementById("tooltip");
  const hits = [];

  POOLS.forEach((pool, i) => {{
    const x = cx(i);
    // Show REJECT-direction bar (higher boundary = stricter = the bottleneck)
    const val = pool.rej;
    const canRej = val >= SPRT_B_ABS;
    const canApp = pool.app >= SPRT_A;
    const color = canRej ? (canApp ? "#22c55e" : "#f59e0b") : "#4E79A7";
    const dark  = canRej ? (canApp ? "#14532d" : "#78350f") : "#1e3a5f";

    const yTop = yS(val);
    const yBot = yS(0);

    const grad = ctx.createLinearGradient(0, yTop, 0, yBot);
    grad.addColorStop(0, color);
    grad.addColorStop(1, dark);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.roundRect(x - bw/2, yTop, bw, yBot - yTop, [4, 4, 0, 0]);
    ctx.fill();

    // Value label
    ctx.fillStyle = "#e2e8f0"; ctx.font = "bold 11px sans-serif"; ctx.textAlign = "center";
    ctx.fillText(val.toFixed(2), x, yTop - 5);

    // Status label
    const status = canRej ? (canApp ? "✓ both" : "✓ REJECT") : "✗ neither";
    ctx.fillStyle = canRej ? "#22c55e" : "#64748b"; ctx.font = "9px sans-serif";
    ctx.fillText(status, x, yTop - 16);

    // X label
    ctx.fillStyle = "#94a3b8"; ctx.font = "bold 12px sans-serif";
    ctx.fillText(`n=${{pool.n}}`, x, PAD.t + ph + 16);
    // Agent names
    ctx.fillStyle = "#475569"; ctx.font = "8px sans-serif";
    pool.agents.slice(0, 2).forEach((ag, j) => {{
      ctx.fillText(ag.split("-")[0], x, PAD.t + ph + 28 + j * 11);
    }});
    if (pool.agents.length > 2) ctx.fillText(`+${{pool.agents.length - 2}} more`, x, PAD.t + ph + 50);

    hits.push({{x, yTop, yBot, bw, pool, val, canRej, canApp}});
  }});

  // Y axis label
  ctx.save();
  ctx.translate(13, PAD.t + ph / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = "#475569"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
  ctx.fillText("|Λ|_max  (REJECT direction)", 0, 0);
  ctx.restore();

  canvas.addEventListener("mousemove", e => {{
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    let best = null;
    hits.forEach(h => {{
      if (mx >= h.x - h.bw/2 - 6 && mx <= h.x + h.bw/2 + 6 && my >= h.yTop - 6 && my <= h.yBot + 6)
        best = h;
    }});
    if (best) {{
      tooltip.style.display = "block";
      tooltip.style.left = (e.clientX + 14) + "px";
      tooltip.style.top  = (e.clientY - 50) + "px";
      const p = best.pool;
      tooltip.innerHTML =
        `<b>n=${{p.n}} agents</b><br>` +
        `Agents: ${{p.agents.join(", ")}}<br>` +
        `max-Λ (REJECT): ${{p.rej}}<br>` +
        `max-Λ (APPROVE): ${{p.app}}<br>` +
        `REJECT boundary reachable: ${{best.canRej ? "✓ YES" : "✗ NO"}}<br>` +
        `APPROVE boundary reachable: ${{best.canApp ? "✓ YES" : "✗ NO"}}`;
    }} else {{
      tooltip.style.display = "none";
    }}
  }});
  canvas.addEventListener("mouseleave", () => {{ tooltip.style.display = "none"; }});
}})();
</script>
</body>
</html>
""".replace("{alpha}", str(ALPHA)).replace("{beta}", str(BETA)).replace("{sprt_b_abs_neg}", f"−{round(abs(SPRT_B), 3)}")


if __name__ == "__main__":
    main()
