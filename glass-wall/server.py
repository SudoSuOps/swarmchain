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
RESEND_KEY = os.environ.get("RESEND_API_KEY", "re_2hEw15wp_6uhiqCTwDFF4E5X4VocBB19c")


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
