"""SwarmOS Flight Sheet Server — serves HTML for browser review + handles approval.

Serves job directories as static files and handles POST /approve/{job_id}
to issue permits from the browser.
"""
from __future__ import annotations

import json
import os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from . import config


class FlightSheetHandler(SimpleHTTPRequestHandler):
    """Serves job files + handles permit approval POST."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(config.JOBS_DIR), **kwargs)

    def do_POST(self):
        if self.path.startswith("/approve/"):
            job_id = self.path.split("/approve/")[1].strip("/")
            self._handle_approve(job_id)
        else:
            self.send_error(404)

    def _handle_approve(self, job_id: str):
        try:
            from .permit import issue_permit
            permit = issue_permit(job_id)

            # Regenerate HTML with permit
            from . import state
            from .flightsheet_html import render_html
            from .profiler import profile as detect_hardware
            from .algos import get as get_algo

            fs = state.load_flightsheet(job_id)
            hw = detect_hardware()
            algo = get_algo(fs.algo) if fs else None
            html = render_html(fs, hw, algo=algo, job_id=job_id, permit=permit)
            html_path = state.job_dir(job_id) / "flightsheet.html"
            html_path.write_text(html)

            response = json.dumps({
                "status": "issued",
                "permit_id": permit.permit_id,
                "job_id": job_id,
                "issued_at": permit.issued_at.isoformat(),
                "flight_sheet_hash": permit.flight_sheet_hash,
            }).encode()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        except Exception as e:
            error = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error)))
            self.end_headers()
            self.wfile.write(error)

    def log_message(self, format, *args):
        # Quiet logging
        pass


def serve(port: int = 8888, host: str = "0.0.0.0"):
    """Start the flight sheet server."""
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), FlightSheetHandler)
    print(f"SwarmOS Flight Sheet Server on http://{host}:{port}/")
    print(f"Serving: {config.JOBS_DIR}")
    server.serve_forever()
