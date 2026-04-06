"""Report generation for ColdCall — JSON + self-contained HTML reports.

Reads all session artifacts (metadata, transcript, metrics, evaluation)
and produces report.json (for CI/CD) and report.html (for sharing/review).
"""

import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("coldcall")


def generate_reports(session_dir: Path) -> tuple[Path, Path]:
    """Generate report.json and report.html for a session directory.

    Returns (json_path, html_path).
    """
    data = _load_session_data(session_dir)

    json_path = _write_json_report(session_dir, data)
    html_path = _write_html_report(session_dir, data)

    log.info(f"Reports generated: {json_path.name}, {html_path.name}")
    return json_path, html_path


def _load_session_data(d: Path) -> dict:
    """Load all JSON artifacts from a session directory."""
    data = {"session_dir": str(d), "session_id": d.name}

    for name in ("metadata", "transcript", "metrics", "evaluation"):
        p = d / f"{name}.json"
        if p.exists():
            data[name] = json.loads(p.read_text())

    # Check which audio files exist
    data["audio_files"] = {}
    for wav in ("mixed_audio.wav", "agent_audio.wav", "caller_audio.wav"):
        p = d / wav
        if p.exists():
            data["audio_files"][wav] = str(p)

    return data


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def _write_json_report(d: Path, data: dict) -> Path:
    """Write a CI-friendly JSON report."""
    meta = data.get("metadata", {})
    ev = data.get("evaluation", {})
    m = data.get("metrics", {})
    lat = m.get("response_latency", {})

    report = {
        "scenario": meta.get("scenario", "unknown"),
        "result": ev.get("overall", "unknown").lower(),
        "duration_seconds": meta.get("duration_seconds"),
        "timestamp": meta.get("start_time"),
        "call_sid": meta.get("call_sid"),
        "criteria": [
            {
                "name": c.get("description", c.get("id", "")),
                "id": c.get("id", ""),
                "result": c.get("result", "unknown").lower(),
                "explanation": c.get("explanation", ""),
            }
            for c in ev.get("criteria", [])
        ],
        "metrics": {
            "latency_p50_ms": _s_to_ms(lat.get("p50")),
            "latency_p95_ms": _s_to_ms(lat.get("p95")),
            "latency_p99_ms": _s_to_ms(lat.get("p99")),
            "latency_mean_ms": _s_to_ms(lat.get("mean")),
            "interruptions": m.get("interruptions", {}).get("count", 0),
            "silence_gaps": m.get("silence_gaps", {}).get("count", 0),
            "turn_count": m.get("turn_count", 0),
        },
        "summary": ev.get("summary", ""),
        "transcript_path": str(d / "transcript.json"),
        "audio_path": str(d / "mixed_audio.wav"),
    }

    path = d / "report.json"
    path.write_text(json.dumps(report, indent=2))
    return path


def _s_to_ms(val) -> int | None:
    """Convert seconds to milliseconds, or None."""
    if val is None:
        return None
    return int(round(val * 1000))


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def _write_html_report(d: Path, data: dict) -> Path:
    """Write a self-contained HTML report with embedded audio and inline CSS/JS."""
    meta = data.get("metadata", {})
    ev = data.get("evaluation", {})
    m = data.get("metrics", {})
    lat = m.get("response_latency", {})
    tx = data.get("transcript", {})
    turns = tx.get("turns", [])

    scenario = meta.get("scenario", "unknown")
    overall = ev.get("overall", "—")
    duration = meta.get("duration_seconds", "—")
    turn_count = meta.get("transcript_turns", len(turns))

    # Embed mixed audio as base64 data URI
    audio_b64 = ""
    wav_path = d / "mixed_audio.wav"
    if wav_path.exists() and wav_path.stat().st_size < 10_000_000:  # < 10MB
        audio_b64 = base64.b64encode(wav_path.read_bytes()).decode("ascii")

    criteria_html = _render_criteria(ev.get("criteria", []))
    transcript_html = _render_transcript(turns)
    metrics_html = _render_metrics(m, lat)

    overall_color = "#22c55e" if overall == "PASS" else "#ef4444" if overall == "FAIL" else "#6b7280"
    timestamp = meta.get("start_time", "")
    summary = ev.get("summary", "")

    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ColdCall Report — {scenario}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #0a0a0a; color: #e5e5e5; padding: 2rem; max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
  h2 {{ font-size: 1.1rem; color: #a3a3a3; margin: 2rem 0 1rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }}
  .subtitle {{ color: #737373; font-size: 0.875rem; margin-bottom: 1.5rem; }}
  .badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.875rem; font-weight: 600; }}
  .badge-pass {{ background: rgba(34,197,94,0.15); color: #22c55e; }}
  .badge-fail {{ background: rgba(239,68,68,0.15); color: #ef4444; }}
  .badge-unknown {{ background: rgba(107,114,128,0.15); color: #6b7280; }}
  .header {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 0.5rem; }}
  .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; margin-bottom: 1.5rem; }}
  .card {{ background: #171717; border: 1px solid #262626; border-radius: 0.75rem; padding: 1rem; text-align: center; }}
  .card-value {{ font-size: 1.5rem; font-weight: 700; }}
  .card-label {{ font-size: 0.75rem; color: #737373; margin-top: 0.25rem; }}
  .section {{ background: #171717; border: 1px solid #262626; border-radius: 0.75rem; padding: 1.25rem; margin-bottom: 1rem; }}
  .criterion {{ display: flex; align-items: flex-start; gap: 0.75rem; margin-bottom: 0.75rem; }}
  .criterion:last-child {{ margin-bottom: 0; }}
  .criterion .badge {{ font-size: 0.75rem; padding: 0.15rem 0.5rem; flex-shrink: 0; margin-top: 0.1rem; }}
  .criterion-id {{ font-family: monospace; font-size: 0.75rem; color: #818cf8; }}
  .criterion-text {{ font-size: 0.875rem; color: #a3a3a3; }}
  .turn {{ display: flex; gap: 0.75rem; margin-bottom: 0.5rem; font-size: 0.875rem; }}
  .turn-time {{ color: #525252; font-size: 0.75rem; width: 3rem; text-align: right; flex-shrink: 0; padding-top: 0.1rem; font-family: monospace; }}
  .turn-speaker {{ font-size: 0.75rem; font-weight: 600; width: 5.5rem; flex-shrink: 0; padding-top: 0.1rem; }}
  .turn-speaker.agent {{ color: #60a5fa; }}
  .turn-speaker.coldcall {{ color: #34d399; }}
  .turn-text {{ color: #d4d4d4; }}
  audio {{ width: 100%; margin: 0.5rem 0; border-radius: 0.5rem; }}
  .summary {{ font-size: 0.875rem; color: #a3a3a3; margin-bottom: 1rem; }}
  .metric-bar {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; }}
  .metric-label {{ font-size: 0.8rem; color: #a3a3a3; width: 8rem; }}
  .metric-value {{ font-size: 0.8rem; font-weight: 600; width: 4rem; }}
  .metric-bar-bg {{ flex: 1; background: #262626; border-radius: 4px; height: 8px; overflow: hidden; }}
  .metric-bar-fill {{ height: 100%; border-radius: 4px; }}
  .footer {{ text-align: center; color: #525252; font-size: 0.75rem; margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #262626; }}
</style>
</head>
<body>

<div class="header">
  <h1>{scenario}</h1>
  <span class="badge badge-{overall.lower() if overall in ('PASS','FAIL') else 'unknown'}">{overall}</span>
</div>
<p class="subtitle">{timestamp} &middot; {duration}s &middot; {turn_count} turns &middot; {meta.get('call_sid', '')}</p>
{f'<p class="summary">{summary}</p>' if summary else ''}

<div class="cards">
  <div class="card">
    <div class="card-value">{duration}s</div>
    <div class="card-label">Duration</div>
  </div>
  <div class="card">
    <div class="card-value">{turn_count}</div>
    <div class="card-label">Turns</div>
  </div>
  <div class="card">
    <div class="card-value">{_s_to_ms(lat.get('p50')) or '—'}<span style="font-size:0.75rem">ms</span></div>
    <div class="card-label">Latency p50</div>
  </div>
  <div class="card">
    <div class="card-value">{m.get('interruptions', dict()).get('count', '—')}</div>
    <div class="card-label">Interruptions</div>
  </div>
</div>

{'<h2>Recording</h2><div class="section"><audio controls src="data:audio/wav;base64,' + audio_b64 + '"></audio></div>' if audio_b64 else ''}

{criteria_html}

{metrics_html}

{transcript_html}

<div class="footer">Generated by ColdCall &middot; {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</div>

</body>
</html>"""

    path = d / "report.html"
    path.write_text(html)
    return path


def _render_criteria(criteria: list) -> str:
    if not criteria:
        return ""
    rows = []
    for c in criteria:
        r = c.get("result", "UNKNOWN")
        cls = "pass" if r == "PASS" else "fail" if r == "FAIL" else "unknown"
        rows.append(f"""\
    <div class="criterion">
      <span class="badge badge-{cls}">{r}</span>
      <div>
        <div class="criterion-id">{c.get('id', '')}</div>
        <div class="criterion-text">{_escape(c.get('explanation', c.get('description', '')))}</div>
      </div>
    </div>""")
    return f'<h2>Evaluation</h2>\n<div class="section">\n{"".join(rows)}\n</div>'


def _render_transcript(turns: list) -> str:
    if not turns:
        return ""
    rows = []
    for t in turns:
        speaker = t.get("speaker", "?")
        cls = "agent" if speaker == "AGENT" else "coldcall"
        ts = t.get("start_time", "?")
        rows.append(f"""\
    <div class="turn">
      <div class="turn-time">{ts}s</div>
      <div class="turn-speaker {cls}">{speaker}</div>
      <div class="turn-text">{_escape(t.get('text', ''))}</div>
    </div>""")
    return f'<h2>Transcript</h2>\n<div class="section">\n{"".join(rows)}\n</div>'


def _render_metrics(m: dict, lat: dict) -> str:
    if not m:
        return ""

    bars = []

    # Latency bars (scale: 0-2000ms)
    for label, key in [("p50", "p50"), ("p95", "p95"), ("p99", "p99"), ("mean", "mean")]:
        val = lat.get(key)
        if val is None:
            continue
        ms = int(round(val * 1000))
        pct = min(100, ms / 20)  # 2000ms = 100%
        color = "#22c55e" if ms < 500 else "#eab308" if ms < 1000 else "#ef4444"
        bars.append(f"""\
    <div class="metric-bar">
      <div class="metric-label">Latency {label}</div>
      <div class="metric-value">{ms}ms</div>
      <div class="metric-bar-bg"><div class="metric-bar-fill" style="width:{pct}%;background:{color}"></div></div>
    </div>""")

    # Interruptions
    ints = m.get("interruptions", {}).get("count", 0)
    bars.append(f"""\
    <div class="metric-bar">
      <div class="metric-label">Interruptions</div>
      <div class="metric-value">{ints}</div>
      <div class="metric-bar-bg"><div class="metric-bar-fill" style="width:{min(100, ints * 20)}%;background:{'#22c55e' if ints == 0 else '#eab308'}"></div></div>
    </div>""")

    # Silence gaps
    gaps = m.get("silence_gaps", {}).get("count", 0)
    bars.append(f"""\
    <div class="metric-bar">
      <div class="metric-label">Silence gaps</div>
      <div class="metric-value">{gaps}</div>
      <div class="metric-bar-bg"><div class="metric-bar-fill" style="width:{min(100, gaps * 20)}%;background:{'#22c55e' if gaps == 0 else '#eab308'}"></div></div>
    </div>""")

    return f'<h2>Metrics</h2>\n<div class="section">\n{"".join(bars)}\n</div>'


def _escape(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
