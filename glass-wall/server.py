#!/usr/bin/env python3
"""SwarmChain Glass-Wall — Sovereign Spectator Surface

Serves the live arena view, proxies /api/ to backend,
and handles /approve/<job_id> for pre-flight approval flow.
"""
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingTCPServer
import urllib.request, urllib.parse, os, mimetypes, json, hashlib
from datetime import datetime, timezone
from pathlib import Path

API = os.environ.get("SWARM_API_URL", "http://localhost:8080")
ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("SWARM_GLASSWALL_PORT", "3000"))
JOBS_DIR = Path(os.environ.get("SWARM_JOBS_DIR", "/data2/swarmchain/jobs"))
HONEY_DIR = Path(os.environ.get("HONEY_DIR", "/data1/swarm-honey"))
RESEND_KEY = os.environ["RESEND_API_KEY"]  # rotated + moved to env 2026-05-29 (was hardcoded)


def _cook_status():
    """Read live cook status from files — no backend needed."""
    # Find the active job (has POJ signed but no closing)
    active = None
    for d in sorted(JOBS_DIR.iterdir()):
        if not d.is_dir(): continue
        if (d / "poj.json").exists() and not (d / "closing.json").exists():
            active = d
    if not active:
        return {"status": "idle", "cooking": False}

    poj = json.loads((active / "poj.json").read_text())
    domain = poj.get("domain", "")
    job_id = active.name
    validated = HONEY_DIR / domain / "validated"

    def _count(f):
        try: return sum(1 for _ in open(f))
        except: return 0

    judged = _count(validated / "judged.jsonl")
    receipts = _count(validated / "receipts.jsonl")

    # Read last 10 verdicts for live feed
    rj = h = p = 0
    scores = []
    recent = []
    judged_file = validated / "judged.jsonl"
    if judged_file.exists():
        lines = open(judged_file).readlines()
        for line in lines:
            try:
                d = json.loads(line.strip())
                s = d.get("score", 0)
                c = d.get("classification", "")
                if c == "royal-jelly": rj += 1
                elif c == "honey": h += 1
                else: p += 1
                if s > 0: scores.append(s)
            except: pass
        for line in lines[-10:]:
            try:
                d = json.loads(line.strip())
                recent.append({
                    "score": d.get("score", 0),
                    "classification": d.get("classification", ""),
                    "judge_ms": d.get("judge_ms", 0),
                    "domain": d.get("domain", ""),
                })
            except: pass

    total = rj + h + p
    return {
        "status": "cooking" if judged < poj.get("pair_count", 0) and judged > 0 else "idle" if judged == 0 else "complete",
        "cooking": judged > 0 and judged < poj.get("pair_count", 0),
        "job_id": job_id,
        "domain": domain,
        "pair_count": poj.get("pair_count", 0),
        "judged": judged,
        "receipts": receipts,
        "royal_jelly": rj,
        "honey": h,
        "propolis": p,
        "avg_score": round(sum(scores) / len(scores), 3) if scores else 0,
        "rj_rate": round(rj / max(total, 1) * 100, 1),
        "progress_pct": round(judged / max(poj.get("pair_count", 1), 1) * 100, 1),
        "recent": recent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _architect_approve(body):
    """Create a job from the architect UI — flight sheet + permit + POJ + sign."""
    import subprocess
    domain = body.get("domain", "")
    pairs = body.get("pairs", 0)
    input_path = body.get("inputPath", "")
    client = body.get("client", "Swarm & Bee")
    fee_tier = body.get("feeTier", "full")

    if not domain or not pairs:
        return {"error": "domain and pairs required"}

    env = os.environ.copy()
    env["PATH"] = "/home/swarm/.local/bin:" + env.get("PATH", "")

    # Generate flight sheet via swarmos CLI
    args = ["swarmos", "flightsheet", domain, "--pairs", str(pairs), "--lock"]
    if input_path:
        args.extend(["--input", input_path])
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=30)

    # Extract job ID from output
    job_id = None
    for line in result.stdout.split("\n"):
        if "Job ID:" in line:
            job_id = line.split("Job ID:")[1].strip()

    if not job_id:
        return {"error": "flight sheet generation failed", "output": result.stdout[-200:]}

    # Permit + POJ + sign
    subprocess.run(["swarmos", "permit", "issue", job_id], env=env, capture_output=True, timeout=10)
    subprocess.run(["swarmos", "poj", "generate", job_id, "--client", client, "--tier", fee_tier], env=env, capture_output=True, timeout=10)
    subprocess.run(["swarmos", "poj", "sign", job_id], env=env, capture_output=True, timeout=10)

    return {"job_id": job_id, "domain": domain, "pairs": pairs, "status": "approved"}


def _architect_send(body):
    """Send preflight email to client from architect UI."""
    import subprocess, hashlib
    domain = body.get("domain", "")
    pairs = body.get("pairs", 0)
    to = body.get("to", "build@swarmandbee.ai")

    # Use Resend CLI with preflight template
    env = os.environ.copy()
    env["PATH"] = "/home/swarm/.resend/bin:/home/swarm/.local/bin:" + env.get("PATH", "")
    env["RESEND_API_KEY"] = RESEND_KEY
    env["DOMAIN"] = domain
    env["PAIR_COUNT"] = str(pairs)
    env["JOB_ID"] = body.get("job_id", "pending")
    env["INPUT_FILE"] = body.get("inputPath", "")
    env["LOCK_HASH"] = "pending"
    env["APPROVE_URL"] = "http://192.168.0.91:3000/architect"

    template_dir = Path(__file__).parent.parent / "templates"
    result = subprocess.run(
        ["bash", str(template_dir / "send.sh"), "preflight",
         f"PRE-FLIGHT — validate-{domain} — {pairs:,} pairs"],
        env={**env, "SWARM_TO": to},
        capture_output=True, text=True, timeout=30,
    )

    return {"sent": True, "to": to, "output": result.stdout[:200]}


def _approve_job(job_id, token):
    """Record approval, issue permit, generate POJ, sign. Returns (ok, message)."""
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return False, "Job not found"

    fs_path = job_dir / "flightsheet.json"
    if not fs_path.exists():
        return False, "No flight sheet"

    fs = json.loads(fs_path.read_text())

    # Verify token matches lock hash
    expected = hashlib.sha256(fs.get("lock_hash", "").encode()).hexdigest()[:32]
    if token != expected:
        return False, "Invalid approval token"

    # Check not already approved
    if (job_dir / "approval.json").exists():
        return True, "Already approved"

    # Write approval
    approval = {
        "job_id": job_id,
        "flight_sheet_id": fs["sheet_id"],
        "flight_sheet_hash": fs["lock_hash"],
        "approved_by": "build@swarmandbee.ai",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "method": "email",
    }
    (job_dir / "approval.json").write_text(json.dumps(approval, indent=2))

    # Auto-issue permit + POJ + sign via swarmos
    try:
        import subprocess
        env = os.environ.copy()
        env["PATH"] = "/home/swarm/.local/bin:" + env.get("PATH", "")
        subprocess.run(["swarmos", "permit", "issue", job_id], env=env, capture_output=True, timeout=10)
        subprocess.run(["swarmos", "poj", "generate", job_id], env=env, capture_output=True, timeout=10)
        subprocess.run(["swarmos", "poj", "sign", job_id], env=env, capture_output=True, timeout=10)
    except Exception as e:
        return True, f"Approved but auto-sign failed: {e}"

    # Send confirmation email
    try:
        import resend
        resend.api_key = RESEND_KEY
        resend.Emails.send({
            "from": "SwarmChain <chain@swarmandbee.ai>",
            "to": ["build@swarmandbee.ai"],
            "subject": f"APPROVED — {fs['domain']} — {fs['pair_count']:,} pairs — Job {job_id}",
            "html": f"""
            <div style="font-family: 'Courier New', monospace; background: #0a0a0a; color: #e0e0e0; padding: 40px;">
              <div style="color: #4caf50; font-size: 24px; letter-spacing: 4px; margin-bottom: 16px;">APPROVED</div>
              <div style="color: #555; margin-bottom: 24px;">
                Job {job_id}<br>
                Domain: {fs['domain']}<br>
                Pairs: {fs['pair_count']:,}<br>
                Approved: {approval['approved_at']}<br>
              </div>
              <div style="color: #f0b000; font-size: 12px; letter-spacing: 2px;">
                PERMIT ISSUED &rarr; POJ GENERATED &rarr; SIGNED<br><br>
                Ready to cook: <code>swarmos run {job_id}</code>
              </div>
              <div style="border-top: 1px solid #222; margin-top: 24px; padding-top: 16px; color: #555; font-size: 11px; letter-spacing: 2px; text-align: center;">
                DEFENDABLE AI INTELLIGENCE REFINERY &mdash; SWARM &amp; BEE
              </div>
            </div>""",
        })
    except Exception:
        pass

    return True, "Approved — permit issued, POJ signed, ready to cook"


def _approval_page(ok, message, job_id):
    color = "#4caf50" if ok else "#f04040"
    status = "APPROVED" if ok else "DENIED"
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>SwarmChain — {status}</title>
<style>
  body {{ font-family: 'Courier New', monospace; background: #0a0a0a; color: #e0e0e0; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
  .card {{ background: #111; border: 1px solid #222; border-radius: 12px; padding: 60px; text-align: center; max-width: 500px; }}
  .status {{ color: {color}; font-size: 32px; letter-spacing: 6px; margin-bottom: 16px; }}
  .msg {{ color: #888; font-size: 14px; margin-bottom: 24px; line-height: 1.6; }}
  .job {{ color: #555; font-size: 11px; letter-spacing: 1px; }}
  .footer {{ color: #333; font-size: 10px; letter-spacing: 2px; margin-top: 32px; }}
  .footer span {{ color: #f0b000; }}
</style></head><body>
<div class="card">
  <div class="status">{status}</div>
  <div class="msg">{message}</div>
  <div class="job">Job: {job_id}</div>
  <div class="footer"><span>SWARM & BEE</span> — DEFENDABLE AI INTELLIGENCE REFINERY</div>
</div>
</body></html>"""


class GlassWallHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0]
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        # ── Approve endpoint ──
        if path.startswith('/approve/'):
            job_id = path.split('/approve/')[1].strip('/')
            token = qs.get('token', [''])[0]
            ok, msg = _approve_job(job_id, token)
            html = _approval_page(ok, msg, job_id).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(html))
            self.end_headers()
            self.wfile.write(html)
            return

        # ── Live cook status (file-based, no backend needed) ──
        if path == '/api/cook-status':
            data = json.dumps(_cook_status()).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
            return

        # ── API proxy ──
        if path.startswith('/api/'):
            qstr = ('?' + self.path.split('?')[1]) if '?' in self.path else ''
            try:
                with urllib.request.urlopen(API + path[4:] + qstr, timeout=10) as r:
                    data = r.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_response(502)
                self.end_headers()
            return

        # ── Static files ──
        if path == '/':
            path = '/index.html'
        fp = os.path.join(ROOT, path.lstrip('/'))
        if os.path.isfile(fp):
            mime = mimetypes.guess_type(fp)[0] or 'text/html'
            with open(fp, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', len(content))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = self.path.split('?')[0]
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}

        # ── Architect: approve (create job internally) ──
        if path == '/api/architect/approve':
            result = _architect_approve(body)
            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
            return

        # ── Architect: send preflight to client ──
        if path == '/api/architect/send':
            result = _architect_send(body)
            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(404)
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    ThreadingTCPServer.allow_reuse_address = True
    print(f"Glass-Wall serving on :{PORT} → API at {API}")
    print(f"Static root: {ROOT}")
    print(f"Jobs dir: {JOBS_DIR}")
    print(f"Approve: http://0.0.0.0:{PORT}/approve/<job_id>?token=<hash>")
    ThreadingTCPServer(('0.0.0.0', PORT), GlassWallHandler).serve_forever()
