"""SwarmOS Flight Sheet — HTML renderer for browser inspection.

Every setting that touches the verdict is visible. No hidden configs.
If the operator can't read it, it can't be defended.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .models import FlightSheet, HardwareProfile, Permit
from .algos import AlgoConfig, get as get_algo
from . import config


def render_html(
    fs: FlightSheet,
    hw: HardwareProfile,
    algo: AlgoConfig | None = None,
    job_id: str = "",
    permit: Permit | None = None,
) -> str:
    """Render a complete flight sheet as inspectable HTML."""
    if algo is None:
        algo = get_algo(fs.algo) or AlgoConfig(name=fs.algo, domain=fs.domain, description="")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Calculate what the judge actually sees
    judge_input_window = 2000   # question chars
    answer_input_window = 14000 # answer chars — covers p95 (13,473) of grants domain

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SwarmOS Flight Sheet — {fs.domain}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Courier New', monospace; background: #0a0a0a; color: #e0e0e0; padding: 40px; max-width: 1000px; margin: 0 auto; }}
  h1 {{ color: #f0b000; font-size: 24px; border-bottom: 2px solid #f0b000; padding-bottom: 10px; margin-bottom: 30px; }}
  h2 {{ color: #f0b000; font-size: 18px; margin: 30px 0 15px 0; border-bottom: 1px solid #333; padding-bottom: 5px; }}
  .section {{ background: #111; border: 1px solid #333; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
  .critical {{ border-color: #f04040; }}
  .critical h2 {{ color: #f04040; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
  th {{ text-align: left; color: #888; font-weight: normal; padding: 6px 12px; border-bottom: 1px solid #333; }}
  td {{ padding: 6px 12px; border-bottom: 1px solid #1a1a1a; }}
  .value {{ color: #4fc3f7; }}
  .warn {{ color: #f0b000; }}
  .danger {{ color: #f04040; }}
  .ok {{ color: #4caf50; }}
  .label {{ color: #888; min-width: 200px; display: inline-block; }}
  pre {{ background: #0d0d0d; border: 1px solid #222; border-radius: 4px; padding: 15px; overflow-x: auto; font-size: 13px; line-height: 1.5; white-space: pre-wrap; color: #ccc; }}
  .status {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-weight: bold; }}
  .status.locked {{ background: #1a3a1a; color: #4caf50; border: 1px solid #4caf50; }}
  .status.draft {{ background: #3a3a1a; color: #f0b000; border: 1px solid #f0b000; }}
  .row {{ display: flex; justify-content: space-between; padding: 4px 0; }}
  .row .label {{ flex: 0 0 250px; }}
  .divider {{ border-top: 1px solid #333; margin: 15px 0; }}
  .footer {{ color: #555; font-size: 12px; margin-top: 40px; text-align: center; }}
</style>
</head>
<body>

<h1>FLIGHT SHEET — {fs.algo.upper()}</h1>

<div class="section">
  <h2>JOB DETAILS</h2>
  <div class="row"><span class="label">Job ID:</span> <span class="value">{job_id or 'pending'}</span></div>
  <div class="row"><span class="label">Domain:</span> <span class="value">{fs.domain}</span></div>
  <div class="row"><span class="label">Algorithm:</span> <span class="value">{fs.algo}</span></div>
  <div class="row"><span class="label">Pairs:</span> <span class="value">{fs.pair_count:,}</span></div>
  <div class="row"><span class="label">Input:</span> <span class="value">{fs.input_path or 'auto-detect'}</span></div>
  <div class="row"><span class="label">Sheet ID:</span> <span class="value">{fs.sheet_id}</span></div>
  <div class="row"><span class="label">Status:</span> <span class="status {'locked' if fs.locked else 'draft'}">{'LOCKED' if fs.locked else 'DRAFT'}</span></div>
  {'<div class="row"><span class="label">Lock Hash:</span> <span class="value">' + (fs.lock_hash or '') + '</span></div>' if fs.locked else ''}
  <div class="row"><span class="label">Generated:</span> <span class="value">{now}</span></div>
</div>

<div class="section">
  <h2>HARDWARE</h2>
  <div class="row"><span class="label">Host:</span> <span class="value">{hw.hostname}</span></div>
  <div class="row"><span class="label">CPU:</span> <span class="value">{hw.cpu.model}</span></div>
  <div class="row"><span class="label">CPU Threads:</span> <span class="value">{hw.cpu.threads}</span></div>
  <div class="row"><span class="label">AMX-INT8:</span> <span class="{'ok' if hw.cpu.amx_int8 else 'danger'}">{'YES' if hw.cpu.amx_int8 else 'NO'}</span></div>
  <div class="row"><span class="label">RAM:</span> <span class="value">{hw.ram_total_gb}GB total / {hw.ram_free_gb}GB free</span></div>
  <div class="divider"></div>
  <table>
    <tr><th>GPU</th><th>Card</th><th>VRAM</th><th>Free</th><th>Power Cap</th></tr>
"""
    for g in hw.gpus:
        html += f'    <tr><td>{g.index}</td><td>{g.name}</td><td>{g.vram_total_gb}GB</td><td class="value">{g.vram_free_gb}GB</td><td>{g.power_limit_w}W</td></tr>\n'

    html += """  </table>
</div>

<div class="section">
  <h2>GPU ASSIGNMENTS</h2>
  <table>
    <tr><th>GPU</th><th>Role</th><th>Model</th><th>Instances</th><th>VRAM</th><th>Power</th><th>Ports</th><th>Hashrate</th></tr>
"""
    for ga in fs.gpu_assignments:
        html += f'    <tr><td>{ga.gpu_index}</td><td class="value">{ga.role.upper()}</td><td>{ga.model_type}</td><td>{ga.instance_count}</td><td>{ga.vram_total_gb}GB ({ga.vram_percent}%)</td><td>{ga.power_target_w}W</td><td>{ga.ports[0]}-{ga.ports[-1]}</td><td>{ga.estimated_hashrate}/min</td></tr>\n'

    html += """  </table>
"""
    if fs.cpu_assignments:
        html += """  <div class="divider"></div>
  <h2>CPU ASSIGNMENTS</h2>
  <table>
    <tr><th>Role</th><th>Model</th><th>Instances</th><th>Threads/inst</th><th>Ports</th><th>Hashrate</th></tr>
"""
        for ca in fs.cpu_assignments:
            html += f'    <tr><td class="value">{ca.role.upper()}</td><td>{ca.model_type}</td><td>{ca.instance_count}</td><td>{ca.threads_per_instance}</td><td>{ca.ports[0]}-{ca.ports[-1]}</td><td>{ca.estimated_hashrate}/min</td></tr>\n'
        html += "  </table>\n"

    html += "</div>\n"

    # CRITICAL SECTION — JUDGE SETTINGS
    html += f"""
<div class="section critical">
  <h2>JUDGE SETTINGS — CRITICAL (affects every verdict)</h2>
  <div class="row"><span class="label">Judge Model:</span> <span class="value">{algo.judge_model}</span></div>
  <div class="row"><span class="label">Judge GGUF:</span> <span class="value">{algo.judge_gguf}</span></div>
  <div class="row"><span class="label">Temperature:</span> <span class="value">{algo.judge_temperature}</span></div>
  <div class="row"><span class="label">Max Tokens (thinking + output):</span> <span class="value">{algo.judge_max_tokens}</span></div>
  <div class="divider"></div>
  <div class="row"><span class="label">Question Input Window:</span> <span class="value">{judge_input_window} chars</span></div>
  <div class="row"><span class="label">Answer Input Window:</span> <span class="{'danger' if answer_input_window < 4000 else 'warn' if answer_input_window < 6000 else 'ok'}">{answer_input_window} chars</span></div>
  <div class="divider"></div>
  <h2>JUDGE SYSTEM PROMPT</h2>
  <pre>{algo.judge_system_prompt}</pre>
  <div class="divider"></div>
  <h2>SCORING THRESHOLDS</h2>
  <div class="row"><span class="label">Royal Jelly:</span> <span class="ok">score &ge; 0.75</span></div>
  <div class="row"><span class="label">Honey:</span> <span class="warn">score 0.50 - 0.74</span></div>
  <div class="row"><span class="label">Wax:</span> <span class="danger">score &lt; 0.50</span></div>
  <div class="row"><span class="label">Verdict Gating:</span> <span class="ok">DISABLED (score-only)</span></div>
</div>

<div class="section critical">
  <h2>RECORDER SETTINGS</h2>
  <div class="row"><span class="label">Recorder Model:</span> <span class="value">{algo.recorder_model}</span></div>
  <div class="row"><span class="label">Recorder GGUF:</span> <span class="value">{algo.recorder_gguf}</span></div>
  <div class="row"><span class="label">Max Tokens:</span> <span class="value">{algo.recorder_max_tokens}</span></div>
  <div class="row"><span class="label">/no_think:</span> <span class="ok">ENABLED</span></div>
  <div class="divider"></div>
  <h2>RECORDER SYSTEM PROMPT</h2>
  <pre>{algo.recorder_system_prompt}</pre>
</div>

<div class="section">
  <h2>MODEL POLICY</h2>
  <div class="row"><span class="label">Fine-tuned models:</span> <span class="ok">ZERO — base models only</span></div>
  <div class="row"><span class="label">Judge:</span> <span class="value">Qwen 3.5 9B Q4_K_M (base, uncompromised)</span></div>
  <div class="row"><span class="label">Recorder:</span> <span class="value">Qwen 3.5 2B Q4_K_M (base, uncompromised)</span></div>
  <div class="row"><span class="label">Warranty:</span> <span class="ok">All verdicts rendered by uncompromised base models</span></div>
</div>

<div class="section">
  <h2>COST ESTIMATES</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Total Models</td><td class="value">{fs.totals.total_models}</td></tr>
    <tr><td>Total VRAM</td><td class="value">{fs.totals.total_vram_used_gb}GB</td></tr>
    <tr><td>Total Power</td><td class="value">{fs.totals.total_power_w}W</td></tr>
    <tr><td>Judge Hashrate</td><td class="value">{fs.totals.judge_hashrate}/min</td></tr>
    <tr><td>Recorder Hashrate</td><td class="value">{fs.totals.recorder_hashrate}/min</td></tr>
    <tr><td>Effective Rate (bottleneck)</td><td class="warn">{fs.totals.total_estimated_hashrate}/min</td></tr>
    <tr><td>Estimated Wall Time</td><td class="value">{fs.totals.estimated_wall_hours:.1f}h</td></tr>
    <tr><td>Cost to Mint (per deed)</td><td class="value">${fs.totals.estimated_cost_to_mint:.6f}</td></tr>
    <tr><td>Total Production Cost</td><td class="value">${fs.totals.estimated_total_cost:.2f}</td></tr>
  </table>
</div>

<div class="section">
  <h2>INPUT DATA PROFILE (site survey)</h2>
  <div class="row"><span class="label">Domain:</span> <span class="value">{fs.domain}</span></div>
  <div class="row"><span class="label">Total Pairs:</span> <span class="value">{fs.pair_count:,}</span></div>
  <div class="row"><span class="label">Input Path:</span> <span class="value">{fs.input_path or 'auto-detect'}</span></div>
  <div class="row"><span class="label">Pair Format:</span> <span class="value">JSONL — messages: [system, user, assistant]</span></div>
  <div class="divider"></div>
  <div style="color: #f0b000; padding: 5px 0;">
    OPERATOR: Verify pair lengths fit the judge input windows above.<br>
    If answers exceed {answer_input_window} chars, the judge sees truncated content and will score lower.
  </div>
</div>

<div class="section">
  <h2>PIPELINE DIAGRAM (mechanical plans)</h2>
  <pre style="color: #4fc3f7; font-size: 14px; line-height: 1.8;">
  SOURCE PAIRS (JSONL)
       │
       ▼
  ┌──────────────────────────────────────────────────┐
  │  JUDGE PHASE — 9B base ({algo.judge_model})       │
  │  {len([g for g in fs.gpu_assignments if g.role=='judge'])} GPU(s), {sum(g.instance_count for g in fs.gpu_assignments if g.role=='judge')} instances              │
  │                                                    │
  │  Input:  question[:{judge_input_window}] + answer[:{answer_input_window}]     │
  │  Output: VERDICT + TOTAL_SCORE + CLASSIFICATION    │
  │  Tokens: {algo.judge_max_tokens} max (thinking + output)          │
  └──────────────┬───────────────────────────────────┘
                 │
                 ▼
          JUDGED BIN (JSONL)
          verdict + score + reasoning + full pair
                 │
                 ▼
  ┌──────────────────────────────────────────────────┐
  │  RECORDER PHASE — 2B base ({algo.recorder_model})  │
  │  {sum(g.instance_count for g in fs.gpu_assignments if g.role=='recorder')} GPU + {sum(c.instance_count for c in fs.cpu_assignments)} CPU + remote fleet         │
  │                                                    │
  │  Input:  verdict + score + question[:500]           │
  │          + answer[:800] + judge reasoning[:400]     │
  │  Output: Structured deed (SEALED)                  │
  │  Tokens: {algo.recorder_max_tokens} max (/no_think = direct output)    │
  └──────────────┬───────────────────────────────────┘
                 │
                 ▼
  ┌──────────────────────────────────────────────────┐
  │  CHAIN — SwarmChain API (:8080)                    │
  │  block/open → attempts → block/finalize            │
  │  Every pair gets a block_id (chain-verifiable)     │
  └──────────────┬───────────────────────────────────┘
                 │
                 ▼
  ┌──────────────────────────────────────────────────┐
  │  CLASSIFICATION — score-only, no verdict gating    │
  │                                                    │
  │  score ≥ 0.75  →  royal-jelly/  (the king)        │
  │  score 0.50    →  honey/        (the knights)      │
  │  score &lt; 0.50  →  propolis/          (defender of the city)       │
  └──────────────────────────────────────────────────┘
  </pre>
</div>

<div class="section critical">
  <h2>DEED DESIGN (architectural rendering)</h2>
  <p style="color: #888; margin-bottom: 15px;">This is what each classified entry looks like. The deed IS the deliverable.</p>

  <h3 style="color: #4caf50; margin: 15px 0 10px;">ROYAL JELLY DEED (score ≥ 0.75)</h3>
  <pre style="border-color: #4caf50;">{{
  "messages": [
    {{"role": "system", "content": "You are a federal grants specialist..."}},
    {{"role": "user", "content": "Write a budget justification for..."}},
    {{"role": "assistant", "content": "Budget Justification: Personnel..."}}
  ],
  "metadata": {{"skill": "budget_justification", "source": "nemotron-235b"}},
  "swarmchain_deed": {{
    "pair_index": 1042,
    "block_id": "a7f3e2b1c9d04e8f",
    "domain": "{fs.domain}",
    "status": "verified",
    "verdict": "PASS",
    "score": 0.88,
    "classification": "royal-jelly",
    "judge_reasoning": "VERDICT: PASS\\nTOTAL_SCORE: 88\\nCLASSIFICATION: royal-jelly\\nREASONING: Comprehensive budget with correct federal rates...",
    "ledger_record": "PAIR_ID: 1042\\nDOMAIN: {fs.domain}\\nPAIR_SUMMARY: Federal grants budget justification with personnel and fringe calculations\\nVERDICT: PASS\\nSCORE: 88\\nCLASSIFICATION: royal-jelly\\nWHY_SEALED: Complete and accurate budget narrative with correct cost categories.\\nRECORD_STATUS: SEALED",
    "energy_ms": 4200,
    "sealed_at": "2026-03-29T18:00:00+00:00"
  }}
}}</pre>

  <h3 style="color: #f0b000; margin: 15px 0 10px;">HONEY DEED (score 0.50 - 0.74)</h3>
  <pre style="border-color: #f0b000;">{{
  "messages": [...],
  "swarmchain_deed": {{
    "pair_index": 2301,
    "block_id": "c4d8f1a2b3e5067a",
    "domain": "{fs.domain}",
    "score": 0.62,
    "classification": "honey",
    "judge_reasoning": "...partial quality, missing indirect cost detail...",
    "ledger_record": "...SEALED",
    "sealed_at": "..."
  }}
}}</pre>

  <h3 style="color: #f04040; margin: 15px 0 10px;">PROPOLIS DEED (score &lt; 0.50)</h3>
  <pre style="border-color: #f04040;">{{
  "messages": [...],
  "swarmchain_deed": {{
    "pair_index": 5102,
    "block_id": "e9b2a7f3d1c80456",
    "domain": "{fs.domain}",
    "score": 0.25,
    "classification": "propolis",
    "judge_reasoning": "...response cuts off mid-sentence, no budget totals...",
    "ledger_record": "...SEALED",
    "sealed_at": "..."
  }}
}}</pre>

  <div class="divider"></div>
  <h3 style="color: #e0e0e0; margin: 10px 0;">REQUIRED DEED FIELDS (non-negotiable)</h3>
  <table>
    <tr><th>Field</th><th>Source</th><th>Required</th></tr>
    <tr><td>messages</td><td>Original pair (user + assistant)</td><td class="ok">YES — the property</td></tr>
    <tr><td>swarmchain_deed.pair_index</td><td>Position in source dataset</td><td class="ok">YES — parcel number</td></tr>
    <tr><td>swarmchain_deed.block_id</td><td>SwarmChain API</td><td class="ok">YES — recording number</td></tr>
    <tr><td>swarmchain_deed.score</td><td>Judge verdict</td><td class="ok">YES — appraisal value</td></tr>
    <tr><td>swarmchain_deed.classification</td><td>Score-only (0.75/0.50)</td><td class="ok">YES — zoning</td></tr>
    <tr><td>swarmchain_deed.judge_reasoning</td><td>Judge output</td><td class="ok">YES — inspection report</td></tr>
    <tr><td>swarmchain_deed.ledger_record</td><td>Recorder output</td><td class="ok">YES — title deed</td></tr>
    <tr><td>swarmchain_deed.sealed_at</td><td>UTC timestamp</td><td class="ok">YES — recording date</td></tr>
    <tr><td>swarmchain_deed.energy_ms</td><td>Inference latency</td><td class="value">YES — construction cost</td></tr>
  </table>
  <div style="color: #f04040; padding: 10px 0; margin-top: 10px;">
    Any deed missing a required field is REJECTED. A deed without a block_id is like a title without a recording number — it cannot be verified and will not ship.
  </div>
</div>

<div class="section">
  <h2>DELIVERABLES</h2>
  <table>
    <tr><th>File</th><th>Contents</th><th>Fields</th></tr>
    <tr><td class="ok">royal_jelly.jsonl</td><td>Full pairs scoring &ge; 0.75</td><td>messages + swarmchain_deed (all fields)</td></tr>
    <tr><td class="warn">honey.jsonl</td><td>Full pairs scoring 0.50 - 0.74</td><td>messages + swarmchain_deed (all fields)</td></tr>
    <tr><td>wax.jsonl</td><td>Full pairs scoring &lt; 0.50</td><td>messages + swarmchain_deed (all fields)</td></tr>
    <tr><td class="value">receipts.jsonl</td><td>Master record — every verdict</td><td>All deed fields (no messages)</td></tr>
    <tr><td class="value">merkle_proof.json</td><td>SHA256 Merkle tree</td><td>Root hash + leaf count + protocol</td></tr>
    <tr><td class="value">closing.json</td><td>Closing statement</td><td>Actuals vs estimates + variance + manifest</td></tr>
  </table>
</div>

<div class="section" id="permit-section" style="border-color: {'#4caf50' if permit else '#f04040'};">
  <h2 style="color: {'#4caf50' if permit else '#f04040'};">PERMIT STATUS: {'ISSUED' if permit else 'NOT ISSUED'}</h2>
"""
    if permit:
        html += f"""
  <div class="row"><span class="label">Permit ID:</span> <span class="ok">{permit.permit_id}</span></div>
  <div class="row"><span class="label">Issued:</span> <span class="ok">{permit.issued_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</span></div>
  <div class="row"><span class="label">Flight Sheet Hash:</span> <span class="value">{permit.flight_sheet_hash[:32]}...</span></div>
  <div class="row"><span class="label">Model Policy:</span> <span class="ok">{permit.model_policy.upper().replace('_', ' ')}</span></div>
  <div class="row"><span class="label">Status:</span> <span class="ok" style="font-size: 18px;">BUILD AUTHORIZED</span></div>
"""
    else:
        html += f"""
  <div style="padding: 20px 0; text-align: center;">
    <p style="color: #f04040; font-size: 16px; margin-bottom: 20px;">
      I have reviewed all settings, judge parameters, input windows,<br>
      scoring thresholds, deed design, and pipeline configuration.
    </p>

    <button id="approve-btn" onclick="approveFlightSheet()" style="
      background: #1a3a1a; color: #4caf50; border: 2px solid #4caf50;
      padding: 16px 48px; font-size: 18px; font-family: 'Courier New', monospace;
      cursor: pointer; border-radius: 6px; letter-spacing: 1px;
      transition: all 0.3s;
    " onmouseover="this.style.background='#2a5a2a'" onmouseout="this.style.background='#1a3a1a'">
      APPROVE FLIGHT SHEET — ISSUE PERMIT
    </button>

    <button onclick="rejectFlightSheet()" style="
      background: #3a1a1a; color: #f04040; border: 2px solid #f04040;
      padding: 16px 32px; font-size: 14px; font-family: 'Courier New', monospace;
      cursor: pointer; border-radius: 6px; margin-left: 20px;
      transition: all 0.3s;
    " onmouseover="this.style.background='#5a2a2a'" onmouseout="this.style.background='#3a1a1a'">
      REJECT — NEEDS REVISION
    </button>

    <div id="permit-result" style="margin-top: 20px; display: none;"></div>
  </div>

  <script>
    async function approveFlightSheet() {{
      const btn = document.getElementById('approve-btn');
      const result = document.getElementById('permit-result');
      btn.disabled = true;
      btn.textContent = 'ISSUING PERMIT...';
      btn.style.opacity = '0.5';

      try {{
        const resp = await fetch('/approve/{job_id}', {{ method: 'POST' }});
        if (resp.ok) {{
          const data = await resp.json();
          result.style.display = 'block';
          result.innerHTML = `
            <div style="background: #1a3a1a; border: 1px solid #4caf50; border-radius: 6px; padding: 20px; text-align: left;">
              <h3 style="color: #4caf50; margin-bottom: 10px;">PERMIT ISSUED</h3>
              <div class="row"><span class="label">Permit ID:</span> <span class="ok">${{data.permit_id}}</span></div>
              <div class="row"><span class="label">Issued:</span> <span class="ok">${{data.issued_at}}</span></div>
              <div class="row"><span class="label">Status:</span> <span class="ok">BUILD AUTHORIZED</span></div>
              <p style="color: #888; margin-top: 15px;">Next: <code>swarmos poj generate {job_id}</code></p>
            </div>
          `;
          btn.textContent = 'PERMIT ISSUED';
          btn.style.background = '#1a3a1a';
        }} else {{
          throw new Error(await resp.text());
        }}
      }} catch(e) {{
        // Fallback — run CLI command
        result.style.display = 'block';
        result.innerHTML = `
          <div style="background: #1a2a3a; border: 1px solid #4fc3f7; border-radius: 6px; padding: 20px;">
            <p style="color: #4fc3f7;">Run this command to issue the permit:</p>
            <pre style="margin-top: 10px;">swarmos permit issue {job_id}</pre>
            <p style="color: #888; margin-top: 10px;">Then: <code>swarmos poj generate {job_id}</code></p>
          </div>
        `;
        btn.textContent = 'APPROVED — RUN CLI COMMAND';
        btn.style.background = '#1a2a3a';
        btn.style.borderColor = '#4fc3f7';
        btn.style.color = '#4fc3f7';
      }}
    }}

    function rejectFlightSheet() {{
      const result = document.getElementById('permit-result');
      result.style.display = 'block';
      result.innerHTML = `
        <div style="background: #3a1a1a; border: 1px solid #f04040; border-radius: 6px; padding: 20px;">
          <h3 style="color: #f04040;">FLIGHT SHEET REJECTED</h3>
          <p style="color: #ccc; margin-top: 10px;">Revise settings and regenerate:</p>
          <pre style="margin-top: 10px;">swarmos flightsheet grants --pairs 43691 --lock --html</pre>
        </div>
      `;
    }}
  </script>
"""
    html += """</div>

<div class="footer">
  SwarmOS v0.1.0 — Swarm &amp; Bee — Defendable Commercial Compute Intelligence Refinery<br>
  Flight sheet generated {now}. Base models only. No trust me bro.
</div>

</body>
</html>""".format(now=now)
    return html
