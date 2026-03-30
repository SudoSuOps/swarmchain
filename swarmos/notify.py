"""SwarmOS Notifications — epoch updates via Resend email.

Sends gate reports, epoch completion, and alerts to the build team.
Every email is a build update — like a construction draw inspection report.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import resend

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "***SECRET_PURGED_FROM_HISTORY***")
FROM_EMAIL = "SwarmOS <build@swarmandbee.ai>"
TO_EMAIL = os.environ.get("SWARM_NOTIFY_EMAIL", "build@swarmandbee.ai")

resend.api_key = RESEND_API_KEY


def send_email(subject: str, html: str, to: str | None = None) -> bool:
    """Send an email via Resend SDK. Returns True on success."""
    try:
        r = resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [to or TO_EMAIL],
            "subject": subject,
            "html": html,
        })
        return r.get("id") is not None
    except Exception:
        return False


def _style():
    return """
    <style>
        body { font-family: 'Courier New', monospace; background: #0a0a0a; color: #e0e0e0; padding: 30px; }
        .header { color: #f0b000; font-size: 22px; border-bottom: 2px solid #f0b000; padding-bottom: 10px; }
        .section { background: #111; border: 1px solid #333; border-radius: 6px; padding: 15px; margin: 15px 0; }
        .ok { color: #4caf50; } .warn { color: #f0b000; } .danger { color: #f04040; } .value { color: #4fc3f7; }
        table { width: 100%; border-collapse: collapse; }
        td, th { padding: 6px 12px; text-align: left; border-bottom: 1px solid #222; }
        th { color: #888; }
        .footer { color: #555; font-size: 11px; margin-top: 30px; text-align: center; }
    </style>
    """


def notify_gate(gate_report: dict, domain: str, job_id: str = "") -> bool:
    """Send a gate inspection report email."""
    g = gate_report["gate"]
    tg = gate_report["total_gates"]
    c = gate_report["classification"]
    pct = g * 25

    # Determine status color
    if c["propolis_pct"] > 70:
        status = "WARNING"
        status_color = "danger"
    elif c["royal_jelly_pct"] > 50:
        status = "STRONG"
        status_color = "ok"
    else:
        status = "ON TRACK"
        status_color = "value"

    subject = f"Gate {g}/{tg} — {domain} epoch ({c['royal_jelly_pct']}% Royal Jelly) [{status}]"

    html = f"""<html><head>{_style()}</head><body>
    <div class="header">GATE {g}/{tg} INSPECTION — {domain.upper()} ({pct}% complete)</div>

    <div class="section">
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Job ID</td><td class="value">{job_id}</td></tr>
            <tr><td>Domain</td><td class="value">{domain}</td></tr>
            <tr><td>Pairs judged (this gate)</td><td class="value">{gate_report['pairs_judged']}</td></tr>
            <tr><td>Rate</td><td class="value">{gate_report['rate_per_min']}/min</td></tr>
            <tr><td>Wall time</td><td class="value">{gate_report['wall_time_sec']:.0f}s</td></tr>
        </table>
    </div>

    <div class="section">
        <h3 style="color: #f0b000;">Classification (cumulative)</h3>
        <table>
            <tr><td>Royal Jelly</td><td class="{status_color}">{c['royal_jelly']} ({c['royal_jelly_pct']}%)</td></tr>
            <tr><td>Honey</td><td class="warn">{c['honey']} ({c['honey_pct']}%)</td></tr>
            <tr><td>Propolis</td><td>{c['propolis']} ({c['propolis_pct']}%)</td></tr>
        </table>
    </div>

    {"<div class='section' style='border-color: #f04040;'><p class='danger'>WARNING: Propolis rate " + str(c['propolis_pct']) + "% — review judge settings before continuing</p></div>" if c['propolis_pct'] > 70 else ""}

    <div class="section">
        <p>Gate {g} of {tg} complete. {'Final gate — ready for finality.' if g == tg else f'Next gate: {g+1}/{tg}'}</p>
    </div>

    <div class="footer">
        SwarmOS v0.1.0 — Swarm & Bee<br>
        Base models only. No trust me bro.<br>
        {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
    </div>
    </body></html>"""

    return send_email(subject, html)


def notify_epoch_complete(domain: str, stats: dict, wall_sec: float, job_id: str = "") -> bool:
    """Send epoch completion email."""
    rj = stats.get("royal-jelly", 0)
    h = stats.get("honey", 0)
    w = stats.get("propolis", 0)
    total = rj + h + w
    rate = total / (wall_sec / 60) if wall_sec > 0 else 0

    subject = f"Epoch Complete — {domain} ({total:,} pairs, {rj/max(total,1)*100:.0f}% Royal Jelly)"

    html = f"""<html><head>{_style()}</head><body>
    <div class="header">EPOCH COMPLETE — {domain.upper()}</div>

    <div class="section">
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Job ID</td><td class="value">{job_id}</td></tr>
            <tr><td>Total pairs</td><td class="value">{total:,}</td></tr>
            <tr><td>Rate</td><td class="value">{rate:.1f}/min</td></tr>
            <tr><td>Wall time</td><td class="value">{wall_sec/3600:.1f}h</td></tr>
        </table>
    </div>

    <div class="section">
        <h3 style="color: #f0b000;">Final Classification</h3>
        <table>
            <tr><td>Royal Jelly (≥0.75)</td><td class="ok">{rj:,} ({rj/max(total,1)*100:.1f}%)</td></tr>
            <tr><td>Honey (0.50-0.74)</td><td class="warn">{h:,} ({h/max(total,1)*100:.1f}%)</td></tr>
            <tr><td>Propolis (<0.50)</td><td>{w:,} ({w/max(total,1)*100:.1f}%)</td></tr>
        </table>
    </div>

    <div class="section">
        <p class="ok">Ready for finality reclassification and closing.</p>
        <p>Next: <code>swarmos close {job_id}</code></p>
    </div>

    <div class="footer">
        SwarmOS v0.1.0 — Swarm & Bee<br>
        Base models only. Defendable.<br>
        {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
    </div>
    </body></html>"""

    return send_email(subject, html)


def notify_alert(domain: str, message: str, job_id: str = "") -> bool:
    """Send an alert email — something needs attention."""
    subject = f"ALERT — {domain} epoch — {message[:60]}"

    html = f"""<html><head>{_style()}</head><body>
    <div class="header" style="color: #f04040; border-color: #f04040;">ALERT — {domain.upper()}</div>

    <div class="section" style="border-color: #f04040;">
        <p class="danger" style="font-size: 16px;">{message}</p>
        <p>Job ID: <span class="value">{job_id}</span></p>
    </div>

    <div class="footer">
        SwarmOS v0.1.0 — Swarm & Bee<br>
        {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
    </div>
    </body></html>"""

    return send_email(subject, html)
