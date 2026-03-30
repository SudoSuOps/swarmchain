"""SwarmOS CLI — the operating system for AI mining.

Usage: swarmos <command> [options]
"""
from __future__ import annotations

import json
import sys

import click

from . import __version__


@click.group()
@click.version_option(__version__, prog_name="SwarmOS")
def main():
    """SwarmOS — The Operating System for AI Mining.

    HiveOS mines coins. SwarmOS mints title deeds.
    """
    pass


# ── profile ────────────────────────────────────────────────

@main.command()
@click.option("--remote", is_flag=True, help="Include remote fleet nodes")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def profile(remote: bool, as_json: bool):
    """Detect and profile all compute hardware."""
    from .profiler import profile as do_profile, format_profile

    hp = do_profile(include_remote=remote)
    if as_json:
        click.echo(hp.model_dump_json(indent=2))
    else:
        click.echo(format_profile(hp))


# ── algo ───────────────────────────────────────────────────

@main.group()
def algo():
    """Algorithm registry commands."""
    pass


@algo.command("list")
def algo_list():
    """List all registered validation algorithms."""
    from .algos import list_algos

    algos = list_algos()
    click.echo(f"{'NAME':<25} {'DOMAIN':<15} DESCRIPTION")
    click.echo("─" * 70)
    for a in algos:
        click.echo(f"{a.name:<25} {a.domain:<15} {a.description}")


@algo.command("show")
@click.argument("name")
def algo_show(name: str):
    """Show details for a specific algorithm."""
    from .algos import get

    a = get(name)
    if not a:
        click.echo(f"Algorithm '{name}' not found", err=True)
        sys.exit(1)
    click.echo(f"Name:           {a.name}")
    click.echo(f"Domain:         {a.domain}")
    click.echo(f"Description:    {a.description}")
    click.echo(f"Judge model:    {a.judge_model}")
    click.echo(f"Recorder model: {a.recorder_model}")
    click.echo(f"Honey >=        {a.honey_threshold}")
    click.echo(f"Jelly >=        {a.jelly_threshold}")
    click.echo(f"Judge tokens:   {a.judge_max_tokens}")
    click.echo(f"Recorder tokens:{a.recorder_max_tokens}")


# ── flightsheet ────────────────────────────────────────────

@main.command()
@click.argument("domain")
@click.option("--pairs", type=int, required=True, help="Number of pairs to validate")
@click.option("--algo", "algo_name", default=None, help="Algorithm name (default: validate-<domain>)")
@click.option("--input", "input_path", default="", help="Input JSONL file path")
@click.option("--lock", is_flag=True, help="Lock the flight sheet immediately")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--html", "as_html", is_flag=True, help="Generate HTML for browser inspection")
def flightsheet(domain: str, pairs: int, algo_name: str | None, input_path: str, lock: bool, as_json: bool, as_html: bool):
    """Generate a flight sheet for a validation job."""
    from .flightsheet import generate, format_flightsheet
    from .profiler import profile as detect_hardware
    from . import state
    from .models import _uuid

    hw = detect_hardware()
    fs = generate(domain, pairs, algo_name=algo_name, hw=hw, input_path=input_path)

    if lock:
        fs.lock()

    # Create a job and save
    job_id = _uuid()
    state.save_flightsheet(job_id, fs)

    if as_html:
        from .flightsheet_html import render_html
        from .algos import get as get_algo
        algo = get_algo(fs.algo)
        html = render_html(fs, hw, algo=algo, job_id=job_id)
        html_path = state.job_dir(job_id) / "flightsheet.html"
        html_path.write_text(html)
        click.echo(f"Flight sheet: {html_path}")
        click.echo(f"Job ID: {job_id}")
        # Try to open in browser (optional)
        import subprocess, shutil
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", str(html_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        click.echo(f"Open in browser: http://192.168.0.91:8888/{job_id}/flightsheet.html")
    elif as_json:
        click.echo(fs.model_dump_json(indent=2))
    else:
        click.echo(format_flightsheet(fs))
        click.echo(f"\nJob ID: {job_id}")
        if not lock:
            click.echo(f"Lock:   swarmos lock {job_id}")


@main.command("lock")
@click.argument("job_id")
def lock_flightsheet(job_id: str):
    """Lock a flight sheet (makes it immutable)."""
    from . import state

    fs = state.load_flightsheet(job_id)
    if not fs:
        click.echo(f"No flight sheet found for job {job_id}", err=True)
        sys.exit(1)
    if fs.locked:
        click.echo(f"Already locked: {fs.lock_hash}")
        return

    h = fs.lock()
    state.save_flightsheet(job_id, fs)
    click.echo(f"Flight sheet LOCKED: {h}")


# ── poj ────────────────────────────────────────────────────

@main.group()
def poj():
    """Proof of Job — pre-closing statement commands."""
    pass


@poj.command("generate")
@click.argument("job_id")
@click.option("--client", default="Swarm & Bee", help="Client name")
@click.option("--tier", default="full", type=click.Choice(["floor", "standard", "full", "enterprise"]))
def poj_generate(job_id: str, client: str, tier: str):
    """Generate a Proof of Job for a locked flight sheet."""
    from . import state
    from .poj import generate_poj, format_poj

    fs = state.load_flightsheet(job_id)
    if not fs:
        click.echo(f"No flight sheet for job {job_id}", err=True)
        sys.exit(1)
    if not fs.locked:
        click.echo("Flight sheet must be locked first. Run: swarmos lock <job_id>", err=True)
        sys.exit(1)

    cal = state.load_calibration(job_id)
    p = generate_poj(job_id, client, fs, calibration=cal, tier=tier)
    state.save_poj(job_id, p)

    click.echo(format_poj(p))


@poj.command("sign")
@click.argument("job_id")
def poj_sign(job_id: str):
    """Sign off on a POJ — authorizes epoch launch."""
    from . import state

    p = state.load_poj(job_id)
    if not p:
        click.echo(f"No POJ found for job {job_id}", err=True)
        sys.exit(1)
    if p.signed:
        click.echo(f"Already signed at {p.signed_at}")
        return

    p.sign()
    state.save_poj(job_id, p)
    click.echo(f"POJ SIGNED — Job {job_id} authorized for launch")
    click.echo(f"Run: swarmos run {job_id}")


@poj.command("show")
@click.argument("job_id")
def poj_show(job_id: str):
    """Display an existing POJ."""
    from . import state
    from .poj import format_poj

    p = state.load_poj(job_id)
    if not p:
        click.echo(f"No POJ found for job {job_id}", err=True)
        sys.exit(1)
    click.echo(format_poj(p))


# ── permit ─────────────────────────────────────────────────

@main.group()
def permit():
    """Build permit — authorize an epoch after flight sheet review."""
    pass


@permit.command("issue")
@click.argument("job_id")
def permit_issue(job_id: str):
    """Issue a build permit for a reviewed flight sheet."""
    from . import state
    from .permit import issue_permit, format_permit

    fs = state.load_flightsheet(job_id)
    if not fs:
        click.echo(f"No flight sheet found for job {job_id}", err=True)
        sys.exit(1)
    if not fs.locked:
        click.echo("Flight sheet must be locked first. Run: swarmos lock <job_id>", err=True)
        sys.exit(1)

    # Check if permit already exists
    existing = state.load_permit(job_id)
    if existing:
        click.echo(f"Permit already issued: {existing.permit_id}")
        click.echo(f"Issued at: {existing.issued_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        click.echo("To re-issue, delete jobs/<job_id>/permit.json and try again.")
        return

    p = issue_permit(job_id)
    click.echo(format_permit(p))
    click.echo(f"\nPermit ISSUED — Job {job_id} authorized for build")
    click.echo(f"Next: swarmos poj generate {job_id}")


@permit.command("show")
@click.argument("job_id")
def permit_show(job_id: str):
    """Display an existing build permit."""
    from . import state
    from .permit import format_permit

    p = state.load_permit(job_id)
    if not p:
        click.echo(f"No permit found for job {job_id}", err=True)
        click.echo("Issue one: swarmos permit issue <job_id>")
        sys.exit(1)
    click.echo(format_permit(p))


@permit.command("verify")
@click.argument("job_id")
def permit_verify(job_id: str):
    """Verify a permit matches the current flight sheet."""
    from .permit import verify_permit

    valid, reason = verify_permit(job_id)
    if valid:
        click.echo(f"VALID: {reason}")
    else:
        click.echo(f"INVALID: {reason}", err=True)
        sys.exit(1)


# ── status ─────────────────────────────────────────────────

@main.command()
@click.argument("job_id", required=False)
def status(job_id: str | None):
    """Show pipeline status for a job or all jobs."""
    from . import state

    if job_id:
        progress = state.load_progress(job_id)
        if progress:
            click.echo(f"Job: {job_id}")
            click.echo(f"  Judged:    {progress.judged}/{progress.pair_count}")
            click.echo(f"  Recorded:  {progress.recorded}/{progress.pair_count}")
            click.echo(f"  Pending:   {progress.pending_in_bin}")
            click.echo(f"  Honey: {progress.honey} | Jelly: {progress.jelly} | Propolis: {progress.propolis}")
            click.echo(f"  Rate:      {progress.recorder_rate:.1f} deeds/min")
            click.echo(f"  ETA:       {progress.eta_sec/3600:.1f}h")
        else:
            poj = state.load_poj(job_id)
            if poj:
                click.echo(f"Job {job_id}: {'signed' if poj.signed else 'awaiting signature'}")
            else:
                click.echo(f"Job {job_id}: no progress data")
    else:
        jobs = state.list_jobs()
        if not jobs:
            click.echo("No jobs found")
            return
        click.echo(f"{'JOB ID':<20} {'STATUS':<12} {'DOMAIN':<15} {'PAIRS':<8} CLIENT")
        click.echo("─" * 70)
        for j in jobs:
            click.echo(
                f"{j['job_id']:<20} {j['status']:<12} "
                f"{j.get('domain', ''):<15} {j.get('pairs', ''):<8} "
                f"{j.get('client', '')}"
            )


# ── calibrate ──────────────────────────────────────────────

@main.command()
@click.argument("job_id")
@click.option("--input", "input_path", default="", help="Input JSONL to sample from")
@click.option("--pairs", "sample_size", type=int, default=50, help="Calibration sample size")
def calibrate(job_id: str, input_path: str, sample_size: int):
    """Run a calibration test (50 pairs) against the flight sheet."""
    from . import state
    from .calibrate import run_calibration, format_calibration

    fs = state.load_flightsheet(job_id)
    if not fs:
        click.echo(f"No flight sheet for job {job_id}", err=True)
        sys.exit(1)

    if not input_path:
        input_path = fs.input_path

    if not input_path:
        click.echo("No input file specified and none in flight sheet", err=True)
        sys.exit(1)

    click.echo(f"Calibrating {sample_size} pairs from {input_path}...")
    report = run_calibration(job_id, fs, input_path, sample_size=sample_size)
    state.save_calibration(job_id, report)
    click.echo(format_calibration(report))


# ── run ────────────────────────────────────────────────────

@main.command("run")
@click.argument("job_id")
@click.option("--resume", is_flag=True, help="Resume from last checkpoint")
def run_epoch_cmd(job_id: str, resume: bool):
    """Execute an epoch from a signed POJ (requires valid permit)."""
    import logging
    from .epoch import run_epoch
    from .permit import verify_permit

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    # Permit gate — mandatory check before anything else
    valid, reason = verify_permit(job_id)
    if not valid:
        click.echo(f"PERMIT DENIED: {reason}", err=True)
        click.echo("Issue a permit: swarmos permit issue <job_id>", err=True)
        sys.exit(1)

    poj = state.load_poj(job_id)
    if not poj:
        click.echo(f"No POJ for job {job_id}", err=True)
        sys.exit(1)
    if not poj.signed:
        click.echo("POJ not signed. Run: swarmos poj sign <job_id>", err=True)
        sys.exit(1)

    click.echo(f"Permit verified. Launching epoch: {poj.domain} | {poj.pair_count:,} pairs")
    progress = run_epoch(job_id, resume=resume)
    click.echo(f"\nEpoch complete: {progress.recorded} deeds sealed")


# ── close ──────────────────────────────────────────────────

@main.command("close")
@click.argument("job_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def close(job_id: str, as_json: bool):
    """Generate closing statement for a completed epoch."""
    from . import state
    from .closing import generate_closing, format_closing

    cs = generate_closing(job_id)
    state.save_closing(job_id, cs)

    if as_json:
        click.echo(cs.model_dump_json(indent=2))
    else:
        click.echo(format_closing(cs))


# ── serve ──────────────────────────────────────────────────

@main.command("serve")
@click.option("--port", default=8888, help="Port to serve on")
def serve_cmd(port: int):
    """Start the flight sheet server for browser review + approval."""
    from .serve import serve
    serve(port=port)


if __name__ == "__main__":
    main()
