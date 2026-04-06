"""ColdCall CLI — benchmark and test voice AI agents."""

import json
import logging
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="coldcall", help="Benchmark and test voice AI agents via cold calls.", no_args_is_help=True)
scenarios_app = typer.Typer(name="scenarios", help="Manage test scenarios.", no_args_is_help=True)
app.add_typer(scenarios_app)

console = Console()

# ---------------------------------------------------------------------------
# coldcall serve
# ---------------------------------------------------------------------------

@app.command()
def serve(
    scenario: str = typer.Option("dental-appointment", help="Scenario name or YAML path"),
    port: int = typer.Option(8080, help="Port to listen on"),
    public_url: str = typer.Option(None, help="Public URL (overrides config)"),
    once: bool = typer.Option(False, help="Exit after one call completes"),
    ci: bool = typer.Option(False, help="CI mode: JSON output, exit 0/1"),
    timeout: int = typer.Option(None, help="Timeout in seconds"),
    config: Path = typer.Option(None, help="Path to coldcall.yaml"),
    scenarios_dir: str = typer.Option(None, "--scenarios", help="Directory of scenario YAMLs"),
):
    """Start the webhook + WebSocket server and listen for calls."""
    import uvicorn
    from coldcall import server
    from coldcall.config import apply_config_to_env, load_config
    from coldcall.scenarios import Scenario

    cfg = load_config(config)
    apply_config_to_env(cfg)

    url = public_url or cfg.server.public_url
    if not url:
        console.print("[red]Error:[/] --public-url is required (or set server.public_url in coldcall.yaml)")
        raise typer.Exit(1)

    p = port or cfg.server.port
    sc = Scenario.from_yaml(scenario)

    ws_scheme = "wss" if url.startswith("https") else "ws"
    host = url.rstrip("/").replace("https://", "").replace("http://", "")
    server.WEBSOCKET_URL = f"{ws_scheme}://{host}/ws"
    server.PUBLIC_URL = url.rstrip("/")
    server.SCENARIO = sc
    server.ONCE_MODE = once
    server.CI_MODE = ci

    if not ci:
        console.print(f"[bold]ColdCall[/] server starting on port {p}")
        console.print(f"  Voice webhook: {url}/voice")
        console.print(f"  WebSocket:     {server.WEBSOCKET_URL}")
        console.print(f"  Dashboard:     {url}/")
        console.print(f"  Scenario:      {sc.name} — {sc.description}")
        console.print(f"  Persona:       {sc.persona.name}")
        console.print(f"  Criteria:      {len(sc.success_criteria)}")
        console.print(f"  Recording:     enabled (dual-channel)")
        if once:
            console.print(f"  Mode:          --once (exit after first call)")
        console.print("Waiting for calls...\n")

    if timeout and once:
        # Start a background timer that kills the server if no call arrives
        import threading
        def _timeout_handler():
            console.print(f"[red]Timeout: no call received within {timeout}s[/]")
            import os, signal
            os.kill(os.getpid(), signal.SIGINT)
        timer = threading.Timer(timeout, _timeout_handler)
        timer.daemon = True
        timer.start()

    uvicorn.run(server.app, host="0.0.0.0", port=p, log_level="warning")

    # After server exits (--once mode or Ctrl+C)
    if ci and once:
        result = server.get_last_result()
        if result and result.get("overall") == "PASS":
            raise typer.Exit(0)
        else:
            raise typer.Exit(1)


# ---------------------------------------------------------------------------
# coldcall test (direct WebSocket — no Twilio needed)
# ---------------------------------------------------------------------------

@app.command()
def test(
    url: str = typer.Argument(..., help="Agent WebSocket URL (ws://host:port/path)"),
    scenario: str = typer.Option("dental-appointment", help="Scenario name or YAML path"),
    sample_rate: int = typer.Option(16000, "--rate", help="Audio sample rate in Hz"),
    protocol: str = typer.Option("raw", help="Audio protocol: raw (binary PCM) or json (base64)"),
    ci: bool = typer.Option(False, help="CI mode: exit 0 on pass, 1 on fail"),
    config: Path = typer.Option(None, help="Path to coldcall.yaml"),
):
    """Test a voice agent via direct WebSocket — no Twilio needed.

    Connects directly to the agent's WebSocket endpoint, plays a persona,
    records the conversation, and evaluates against success criteria.

    \b
    Examples:
      coldcall test ws://localhost:8080/ws
      coldcall test wss://agent.example.com/audio --scenario angry-refund
      coldcall test ws://localhost:8080/ws --rate 8000 --protocol json
    """
    import asyncio
    from coldcall.config import apply_config_to_env, load_config
    from coldcall.scenarios import Scenario

    cfg = load_config(config)
    apply_config_to_env(cfg)

    sc = Scenario.from_yaml(scenario)

    console.print(f"[bold]ColdCall[/] direct test")
    console.print(f"  Agent:     {url}")
    console.print(f"  Scenario:  {sc.name} — {sc.description}")
    console.print(f"  Persona:   {sc.persona.name}")
    console.print(f"  Protocol:  {protocol} @ {sample_rate}Hz")
    console.print()

    from coldcall.direct import run_direct_test
    result = asyncio.run(run_direct_test(url, sc, sample_rate=sample_rate, protocol=protocol))

    if result:
        overall = result.get("overall", "UNKNOWN")
        color = "green" if overall == "PASS" else "red"
        passed = sum(1 for c in result.get("criteria", []) if c.get("result") == "PASS")
        total = len(result.get("criteria", []))
        console.print(f"\n[bold]Result:[/] [{color}]{overall}[/{color}] ({passed}/{total} criteria)")
        console.print(f"Summary: {result.get('summary', '')}")

    if ci:
        if result and result.get("overall") == "PASS":
            raise typer.Exit(0)
        else:
            raise typer.Exit(1)


# ---------------------------------------------------------------------------
# coldcall call (outbound via Twilio)
# ---------------------------------------------------------------------------

@app.command()
def call(
    to: str = typer.Argument(..., help="Phone number to call (e.g. +14155559876)"),
    public_url: str = typer.Option(None, help="Public URL of running server"),
    config: Path = typer.Option(None, help="Path to coldcall.yaml"),
):
    """Make an outbound call to a target agent."""
    from coldcall.config import apply_config_to_env, load_config
    from coldcall.phone import make_outbound_call

    cfg = load_config(config)
    apply_config_to_env(cfg)

    url = public_url or cfg.server.public_url
    if not url:
        console.print("[red]Error:[/] --public-url required")
        raise typer.Exit(1)

    ws_scheme = "wss" if url.startswith("https") else "ws"
    host = url.rstrip("/").replace("https://", "").replace("http://", "")
    websocket_url = f"{ws_scheme}://{host}/ws"

    console.print(f"Calling {to}...")
    call_sid = make_outbound_call(to, url.rstrip("/"), websocket_url)
    console.print(f"\nCall in progress. Watch the serve terminal.")
    console.print(f"Call SID: {call_sid}")


# ---------------------------------------------------------------------------
# coldcall setup
# ---------------------------------------------------------------------------

@app.command()
def setup(
    provider: str = typer.Option("twilio", help="Provider to configure"),
    webhook_url: str = typer.Option(None, help="Public URL for webhooks"),
    area_code: str = typer.Option("415", help="US area code for number"),
    config: Path = typer.Option(None, help="Path to coldcall.yaml"),
):
    """Set up telephony provider (buy/configure phone number)."""
    from coldcall.config import apply_config_to_env, load_config
    from coldcall.phone import provision

    cfg = load_config(config)
    apply_config_to_env(cfg)

    if provider != "twilio":
        console.print(f"[red]Error:[/] Unknown provider '{provider}'. Supported: twilio")
        raise typer.Exit(1)

    url = webhook_url or cfg.server.public_url
    if not url:
        console.print("[red]Error:[/] --webhook-url required (or set server.public_url in coldcall.yaml)")
        raise typer.Exit(1)

    number = provision(webhook_url=f"{url.rstrip('/')}/voice", area_code=area_code)
    console.print(f"\n[green]Ready.[/] Call {number} to test.")


# ---------------------------------------------------------------------------
# coldcall scenarios list
# ---------------------------------------------------------------------------

@scenarios_app.command("list")
def scenarios_list():
    """List available scenarios."""
    from coldcall.scenarios import Scenario, list_scenarios

    names = list_scenarios()
    if not names:
        console.print("No scenarios found.")
        return

    table = Table(title="Available Scenarios")
    table.add_column("Name", style="cyan")
    table.add_column("Persona", style="green")
    table.add_column("Criteria", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Description")

    for name in names:
        s = Scenario.from_yaml(name)
        table.add_row(name, s.persona.name, str(len(s.success_criteria)), f"{s.max_duration_seconds}s", s.description[:50])

    console.print(table)


# ---------------------------------------------------------------------------
# coldcall scenarios init
# ---------------------------------------------------------------------------

SCENARIO_TEMPLATE = """\
name: {name}
description: ""
persona: |
  You are [Name], calling to [purpose].
  Your name is [Full Name]. Your phone number is 555-XXXX.
goal: ""
max_duration_seconds: 120
success_criteria:
  - "agent greeted the caller professionally"
  - "agent completed the caller's request"
  - "agent confirmed the outcome before ending the call"
"""

@scenarios_app.command("init")
def scenarios_init(
    name: str = typer.Argument(None, help="Scenario name. Omit to copy all built-in scenarios."),
):
    """Create a new scenario from template, or copy all built-ins to ./scenarios/."""
    from coldcall.scenarios import SCENARIOS_DIR

    local_dir = Path("scenarios")
    local_dir.mkdir(exist_ok=True)

    if name is None:
        count = 0
        for src in sorted(SCENARIOS_DIR.glob("*.yaml")):
            dst = local_dir / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
                count += 1
                console.print(f"  Copied {src.name}")
            else:
                console.print(f"  Skipped {src.name} (exists)")
        console.print(f"\n[green]{count} scenarios copied to ./scenarios/[/]")
    else:
        path = local_dir / f"{name}.yaml"
        if path.exists():
            console.print(f"[red]Error:[/] {path} already exists")
            raise typer.Exit(1)
        path.write_text(SCENARIO_TEMPLATE.format(name=name))
        console.print(f"[green]Created {path}[/] — edit it to define your scenario.")


# ---------------------------------------------------------------------------
# coldcall results
# ---------------------------------------------------------------------------

@app.command()
def results(
    session_dir: str = typer.Argument(None, help="Path to session directory"),
    last: bool = typer.Option(False, "--last", help="Show the most recent result"),
    ci: bool = typer.Option(False, "--ci", help="Output raw JSON"),
):
    """Show results from test runs."""
    results_dir = Path("results")

    if last:
        if not results_dir.exists():
            console.print("[red]No results directory found[/]")
            raise typer.Exit(1)
        dirs = sorted([d for d in results_dir.iterdir() if d.is_dir() and not d.name.startswith(".")], reverse=True)
        if not dirs:
            console.print("[red]No results found[/]")
            raise typer.Exit(1)
        session_dir = str(dirs[0])

    if not session_dir:
        _list_results(results_dir)
        return

    d = Path(session_dir)
    if not d.exists():
        console.print(f"[red]Not found:[/] {d}")
        raise typer.Exit(1)

    if ci:
        out = {}
        for f in d.glob("*.json"):
            out[f.stem] = json.loads(f.read_text())
        print(json.dumps(out, indent=2))
        return

    _print_result_detail(d)


def _list_results(results_dir: Path):
    if not results_dir.exists():
        console.print("No results yet.")
        return
    dirs = sorted([d for d in results_dir.iterdir() if d.is_dir() and not d.name.startswith(".")], reverse=True)

    table = Table(title="Call Results")
    table.add_column("Timestamp", style="cyan")
    table.add_column("Scenario")
    table.add_column("Result", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Turns", justify="right")

    for d in dirs[:20]:
        meta_path = d / "metadata.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        overall = "—"
        eval_path = d / "evaluation.json"
        if eval_path.exists():
            ev = json.loads(eval_path.read_text())
            overall = "[green]PASS[/]" if ev.get("overall") == "PASS" else "[red]FAIL[/]"
        table.add_row(d.name, meta.get("scenario", "?"), overall, f"{meta.get('duration_seconds', '?')}s", str(meta.get("transcript_turns", "?")))

    console.print(table)


def _print_result_detail(d: Path):
    meta_path = d / "metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        console.print(f"\n[bold]Session:[/] {d.name}")
        console.print(f"  Scenario:  {meta.get('scenario')}")
        console.print(f"  Duration:  {meta.get('duration_seconds')}s")
        console.print(f"  Turns:     {meta.get('transcript_turns')}")
        console.print(f"  Call SID:  {meta.get('call_sid')}")

    eval_path = d / "evaluation.json"
    if eval_path.exists():
        ev = json.loads(eval_path.read_text())
        overall = ev.get("overall", "?")
        color = "green" if overall == "PASS" else "red"
        console.print(f"\n[bold]Evaluation:[/] [{color}]{overall}[/{color}]")
        console.print(f"  {ev.get('summary', '')}")
        table = Table()
        table.add_column("Criterion")
        table.add_column("Result", justify="center")
        table.add_column("Explanation")
        for c in ev.get("criteria", []):
            r = c.get("result", "?")
            rc = "green" if r == "PASS" else "red"
            table.add_row(c.get("id", "?"), f"[{rc}]{r}[/{rc}]", c.get("explanation", ""))
        console.print(table)

    metrics_path = d / "metrics.json"
    if metrics_path.exists():
        m = json.loads(metrics_path.read_text())
        lat = m.get("response_latency", {})
        console.print(f"\n[bold]Metrics:[/]")
        console.print(f"  Latency p50={lat.get('p50')}s  p95={lat.get('p95')}s  mean={lat.get('mean')}s")
        console.print(f"  Interruptions: {m.get('interruptions', {}).get('count', 0)}")
        console.print(f"  Silence gaps:  {m.get('silence_gaps', {}).get('count', 0)}")

    transcript_path = d / "transcript.json"
    if transcript_path.exists():
        tx = json.loads(transcript_path.read_text())
        turns = tx.get("turns", [])
        if turns:
            console.print(f"\n[bold]Transcript:[/]")
            for t in turns:
                speaker = t["speaker"]
                sc = "blue" if speaker == "AGENT" else "green"
                console.print(f"  [{sc}][{t.get('start_time', '?')}s] {speaker}:[/{sc}] {t['text']}")


# ---------------------------------------------------------------------------
# coldcall report
# ---------------------------------------------------------------------------

@app.command()
def report(
    session_dir: str = typer.Argument(None, help="Path to session directory"),
    last: bool = typer.Option(False, "--last", help="Generate for most recent session"),
):
    """Generate JSON + HTML reports for a session."""
    from coldcall.report import generate_reports

    results_dir = Path("results")

    if last:
        if not results_dir.exists():
            console.print("[red]No results directory found[/]")
            raise typer.Exit(1)
        dirs = sorted([d for d in results_dir.iterdir() if d.is_dir() and not d.name.startswith(".")], reverse=True)
        if not dirs:
            console.print("[red]No results found[/]")
            raise typer.Exit(1)
        session_dir = str(dirs[0])

    if not session_dir:
        console.print("[red]Specify a session directory or use --last[/]")
        raise typer.Exit(1)

    d = Path(session_dir)
    json_path, html_path = generate_reports(d)

    console.print(f"[green]Reports generated:[/]")
    console.print(f"  JSON: {json_path}")
    console.print(f"  HTML: {html_path}")

    # Print the JSON report summary
    report_data = json.loads(json_path.read_text())
    result = report_data.get("result", "unknown")
    color = "green" if result == "pass" else "red"
    console.print(f"\n  Result: [{color}]{result.upper()}[/{color}]")
    console.print(f"  Scenario: {report_data.get('scenario')}")

    m = report_data.get("metrics", {})
    console.print(f"  Latency p50: {m.get('latency_p50_ms')}ms  p95: {m.get('latency_p95_ms')}ms")


# ---------------------------------------------------------------------------
# coldcall evaluate
# ---------------------------------------------------------------------------

@app.command()
def evaluate(
    session_dir: str = typer.Argument(..., help="Path to session directory"),
    scenario: str = typer.Option("dental-appointment", help="Scenario name or YAML path"),
    config: Path = typer.Option(None, help="Path to coldcall.yaml"),
):
    """Run LLM judge evaluation on a session transcript."""
    from coldcall.config import apply_config_to_env, load_config
    from coldcall.judge import evaluate_session
    from coldcall.scenarios import Scenario

    cfg = load_config(config)
    apply_config_to_env(cfg)

    d = Path(session_dir)
    sc = Scenario.from_yaml(scenario)
    result = evaluate_session(d, sc)

    passed = sum(1 for c in result.get("criteria", []) if c.get("result") == "PASS")
    total = len(result.get("criteria", []))
    console.print(f"\n[bold]Overall:[/] {result.get('overall')} ({passed}/{total})")
    console.print(f"Summary: {result.get('summary')}")


# ---------------------------------------------------------------------------
# coldcall metrics
# ---------------------------------------------------------------------------

@app.command()
def metrics(
    session_dir: str = typer.Argument(..., help="Path to session directory"),
):
    """Compute audio metrics for a session."""
    from coldcall.metrics import compute_metrics

    d = Path(session_dir)
    m = compute_metrics(d)

    lat = m["response_latency"]
    console.print(f"\n[bold]Response latency[/] ({lat['count']} samples):")
    console.print(f"  p50={lat['p50']}s  p95={lat['p95']}s  p99={lat['p99']}s  mean={lat['mean']}s")
    console.print(f"Interruptions: {m['interruptions']['count']}")
    console.print(f"Silence gaps:  {m['silence_gaps']['count']}")
    console.print(f"Call duration:  {m['call_duration_seconds']}s")
    console.print(f"Turn count:    {m['turn_count']}")
    console.print(f"\nSaved to {d / 'metrics.json'}")


# ---------------------------------------------------------------------------
# coldcall recording
# ---------------------------------------------------------------------------

@app.command()
def recording(
    recording_sid: str = typer.Argument(..., help="Twilio Recording SID (RE...)"),
    output: str = typer.Option(None, "-o", "--output", help="Output file path"),
    config: Path = typer.Option(None, help="Path to coldcall.yaml"),
):
    """Download a call recording from Twilio."""
    from coldcall.config import apply_config_to_env, load_config
    from coldcall.phone import download_recording

    cfg = load_config(config)
    apply_config_to_env(cfg)

    out = output or f"{recording_sid}.mp3"
    download_recording(recording_sid, out)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    app()
