"""Webhook + WebSocket server + REST API + dashboard for ColdCall."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("coldcall")

app = FastAPI(title="coldcall")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set by CLI at startup
WEBSOCKET_URL: str = ""
PUBLIC_URL: str = ""
SCENARIO: object = None
ONCE_MODE: bool = False
CI_MODE: bool = False

RESULTS_DIR = Path("results")
SCENARIOS_DIR = Path("scenarios")

# ---------------------------------------------------------------------------
# Twilio webhooks
# ---------------------------------------------------------------------------

@app.post("/voice")
async def voice(request: Request):
    form = await request.form()
    caller = form.get("From", "unknown")
    call_sid = form.get("CallSid", "unknown")
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    log.info(f"[{ts}] INCOMING CALL from {caller} (CallSid: {call_sid})")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Start>
        <Recording name="coldcall" track="both" channels="dual"
                   recordingStatusCallback="{PUBLIC_URL}/recording-status"
                   recordingStatusCallbackEvent="in-progress completed"
                   trim="do-not-trim" />
    </Start>
    <Connect>
        <Stream url="{WEBSOCKET_URL}" />
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.post("/voice/status")
async def status(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    call_status = form.get("CallStatus", "unknown")
    duration = form.get("CallDuration", "n/a")
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    log.info(f"[{ts}] STATUS {call_status} for {call_sid} (duration: {duration}s)")
    return Response(status_code=204)


@app.post("/recording-status")
async def recording_status(request: Request):
    form = await request.form()
    rec_sid = form.get("RecordingSid", "unknown")
    rec_status = form.get("RecordingStatus", "unknown")
    rec_url = form.get("RecordingUrl", "")
    call_sid = form.get("CallSid", "unknown")
    duration = form.get("RecordingDuration", "n/a")
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    log.info(f"[{ts}] RECORDING {rec_status} sid={rec_sid} call={call_sid} duration={duration}s")
    if rec_status == "completed" and rec_url:
        log.info(f"  Download: {rec_url}.mp3")
    return Response(status_code=204)


_last_result: dict | None = None


def get_last_result() -> dict | None:
    return _last_result


@app.websocket("/ws")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    from coldcall.bot import run_bot

    def _on_complete(session_dir, evaluation):
        global _last_result
        _last_result = evaluation
        if ONCE_MODE:
            import os
            import signal
            # In CI/once mode: signal the server to shut down after the call
            log.info("--once mode: shutting down after call")
            os.kill(os.getpid(), signal.SIGINT)

    try:
        await run_bot(websocket, scenario=SCENARIO, on_call_complete=_on_complete)
    except Exception:
        log.exception("Bot pipeline error")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# REST API — Scenarios
# ---------------------------------------------------------------------------

@app.get("/api/scenarios")
async def api_list_scenarios():
    from coldcall.scenarios import Scenario, list_scenarios
    out = []
    for name in list_scenarios():
        s = Scenario.from_yaml(name)
        out.append({
            "name": s.name,
            "description": s.description,
            "goal": s.goal,
            "persona_name": s.persona.name,
            "criteria_count": len(s.success_criteria),
            "max_duration_seconds": s.max_duration_seconds,
        })
    return out


@app.get("/api/scenarios/{name}")
async def api_get_scenario(name: str):
    from coldcall.scenarios import Scenario
    s = Scenario.from_yaml(name)
    return {
        "name": s.name,
        "description": s.description,
        "goal": s.goal,
        "max_duration_seconds": s.max_duration_seconds,
        "persona": {
            "name": s.persona.name,
            "phone": s.persona.phone,
            "voice_id": s.persona.voice_id,
            "system_prompt": s.persona.system_prompt,
        },
        "success_criteria": [{"id": c.id, "description": c.description} for c in s.success_criteria],
    }


@app.post("/api/scenarios")
async def api_create_scenario(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return Response(status_code=400, content="name is required")

    SCENARIOS_DIR.mkdir(exist_ok=True)
    path = SCENARIOS_DIR / f"{name}.yaml"
    if path.exists():
        return Response(status_code=409, content=f"Scenario '{name}' already exists")

    # Build YAML data
    data = {
        "name": name,
        "description": body.get("description", ""),
        "goal": body.get("goal", ""),
        "max_duration_seconds": body.get("max_duration_seconds", 120),
        "persona": body.get("persona", ""),
        "success_criteria": body.get("success_criteria", []),
    }
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True))
    return Response(status_code=201, content=json.dumps({"name": name}), media_type="application/json")


@app.put("/api/scenarios/{name}")
async def api_update_scenario(name: str, request: Request):
    path = SCENARIOS_DIR / f"{name}.yaml"
    if not path.exists():
        return Response(status_code=404, content=f"Scenario '{name}' not found")

    body = await request.json()
    data = {
        "name": body.get("name", name),
        "description": body.get("description", ""),
        "goal": body.get("goal", ""),
        "max_duration_seconds": body.get("max_duration_seconds", 120),
        "persona": body.get("persona", ""),
        "success_criteria": body.get("success_criteria", []),
    }
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True))
    return {"name": name, "status": "updated"}


@app.delete("/api/scenarios/{name}")
async def api_delete_scenario(name: str):
    path = SCENARIOS_DIR / f"{name}.yaml"
    if path.exists():
        path.unlink()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# REST API — Results
# ---------------------------------------------------------------------------

@app.get("/api/results")
async def api_list_results():
    if not RESULTS_DIR.exists():
        return []
    out = []
    for d in sorted(RESULTS_DIR.iterdir(), reverse=True):
        if not d.is_dir() or d.name.startswith("."):
            continue
        meta_path = d / "metadata.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        item = {
            "id": d.name,
            "scenario": meta.get("scenario"),
            "duration_seconds": meta.get("duration_seconds"),
            "transcript_turns": meta.get("transcript_turns"),
            "start_time": meta.get("start_time"),
        }
        eval_path = d / "evaluation.json"
        if eval_path.exists():
            ev = json.loads(eval_path.read_text())
            item["overall"] = ev.get("overall")
            item["summary"] = ev.get("summary")
        out.append(item)
    return out


@app.get("/api/results/latest")
async def api_latest_result():
    if not RESULTS_DIR.exists():
        return Response(status_code=404)
    dirs = sorted([d for d in RESULTS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")], reverse=True)
    if not dirs:
        return Response(status_code=404)
    return _load_session(dirs[0])


@app.get("/api/results/{session_id}")
async def api_get_result(session_id: str):
    d = RESULTS_DIR / session_id
    if not d.exists():
        return Response(status_code=404)
    return _load_session(d)


@app.delete("/api/results/{session_id}")
async def api_delete_result(session_id: str):
    import shutil
    d = RESULTS_DIR / session_id
    if d.exists():
        shutil.rmtree(d)
    return Response(status_code=204)


def _load_session(d: Path) -> dict:
    out = {"id": d.name}
    for f in d.glob("*.json"):
        out[f.stem] = json.loads(f.read_text())
    return out


# ---------------------------------------------------------------------------
# Dashboard — Serve React SPA
# ---------------------------------------------------------------------------

DASHBOARD_DIR = Path(__file__).parent / "dashboard_dist"

if DASHBOARD_DIR.exists() and (DASHBOARD_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=DASHBOARD_DIR / "assets"), name="dashboard-assets")

    @app.get("/dashboard/{full_path:path}")
    async def serve_dashboard(full_path: str):
        return FileResponse(DASHBOARD_DIR / "index.html")

    @app.get("/dashboard")
    async def serve_dashboard_root():
        return FileResponse(DASHBOARD_DIR / "index.html")

# Inline dashboard fallback when React build is not available
@app.get("/")
async def dashboard_index():
    if DASHBOARD_DIR.exists() and (DASHBOARD_DIR / "index.html").exists():
        return FileResponse(DASHBOARD_DIR / "index.html")
    return HTMLResponse(_INLINE_DASHBOARD)


# ---------------------------------------------------------------------------
# Inline single-file dashboard (no build step needed)
# ---------------------------------------------------------------------------

_INLINE_DASHBOARD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ColdCall Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={theme:{extend:{colors:{brand:'#6366f1'}}}}</script>
<style>
  body { font-family: 'Inter', system-ui, sans-serif; }
  .fade-in { animation: fadeIn 0.3s ease-in; }
  @keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:none} }
</style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">

<div id="app" class="flex h-screen">
  <!-- Sidebar -->
  <nav class="w-56 bg-gray-900 border-r border-gray-800 flex flex-col p-4 shrink-0">
    <h1 class="text-xl font-bold text-brand mb-8">ColdCall</h1>
    <a onclick="navigate('scenarios')" class="nav-link cursor-pointer px-3 py-2 rounded-lg mb-1 hover:bg-gray-800 transition">Scenarios</a>
    <a onclick="navigate('results')" class="nav-link cursor-pointer px-3 py-2 rounded-lg mb-1 hover:bg-gray-800 transition">Results</a>
    <a onclick="navigate('create')" class="nav-link cursor-pointer px-3 py-2 rounded-lg mb-1 hover:bg-gray-800 transition">+ New Scenario</a>
    <div class="mt-auto text-xs text-gray-600 pt-4">v0.1.0</div>
  </nav>

  <!-- Main content -->
  <main id="content" class="flex-1 overflow-auto p-8"></main>
</div>

<script>
const API = '';
let currentPage = 'scenarios';

function esc(s) { if(!s) return ''; const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

function navigate(page, data) {
  currentPage = page;
  document.querySelectorAll('.nav-link').forEach(el => el.classList.remove('bg-gray-800', 'text-white'));
  if (page === 'scenarios' || page === 'results' || page === 'create') {
    const links = document.querySelectorAll('.nav-link');
    const idx = page === 'scenarios' ? 0 : page === 'results' ? 1 : 2;
    if (links[idx]) links[idx].classList.add('bg-gray-800', 'text-white');
  }
  render(page, data);
}

async function render(page, data) {
  const el = document.getElementById('content');
  try {
    if (page === 'scenarios') await renderScenarios(el);
    else if (page === 'results') await renderResults(el);
    else if (page === 'result-detail') await renderResultDetail(el, data);
    else if (page === 'scenario-detail') await renderScenarioDetail(el, data);
    else if (page === 'create') renderCreateScenario(el);
  } catch(e) { el.innerHTML = `<p class="text-red-400">Error: ${e.message}</p>`; }
}

// --- Scenarios Page ---
async function renderScenarios(el) {
  const res = await fetch(`${API}/api/scenarios`);
  const scenarios = await res.json();
  el.innerHTML = `
    <div class="fade-in">
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-2xl font-bold">Scenarios</h2>
        <button onclick="navigate('create')" class="bg-brand hover:bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm transition">+ New Scenario</button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        ${scenarios.map(s => `
          <div onclick="navigate('scenario-detail','${s.name}')" class="bg-gray-900 border border-gray-800 rounded-xl p-5 cursor-pointer hover:border-brand transition">
            <h3 class="font-semibold text-white mb-1">${esc(s.name)}</h3>
            <p class="text-sm text-gray-400 mb-3">${esc(s.description)}</p>
            <div class="flex gap-4 text-xs text-gray-500">
              <span>${s.persona_name}</span>
              <span>${s.criteria_count} criteria</span>
              <span>${s.max_duration_seconds}s max</span>
            </div>
          </div>
        `).join('')}
      </div>
    </div>`;
}

// --- Scenario Detail ---
async function renderScenarioDetail(el, name) {
  const res = await fetch(`${API}/api/scenarios/${name}`);
  const s = await res.json();
  el.innerHTML = `
    <div class="fade-in max-w-3xl">
      <button onclick="navigate('scenarios')" class="text-sm text-gray-500 hover:text-white mb-4 inline-block">&larr; Back</button>
      <h2 class="text-2xl font-bold mb-1">${esc(s.name)}</h2>
      <p class="text-gray-400 mb-6">${esc(s.description)}</p>
      <div class="grid grid-cols-2 gap-6 mb-6">
        <div class="bg-gray-900 rounded-xl p-4 border border-gray-800">
          <h4 class="text-xs text-gray-500 uppercase mb-2">Goal</h4>
          <p class="text-sm">${esc(s.goal)}</p>
        </div>
        <div class="bg-gray-900 rounded-xl p-4 border border-gray-800">
          <h4 class="text-xs text-gray-500 uppercase mb-2">Persona</h4>
          <p class="text-sm font-medium">${s.persona.name}</p>
          <p class="text-xs text-gray-400 mt-1">${s.persona.phone || 'No phone'} &middot; ${s.max_duration_seconds}s max</p>
        </div>
      </div>
      <div class="bg-gray-900 rounded-xl p-4 border border-gray-800 mb-6">
        <h4 class="text-xs text-gray-500 uppercase mb-2">System Prompt</h4>
        <pre class="text-sm text-gray-300 whitespace-pre-wrap">${esc(s.persona.system_prompt)}</pre>
      </div>
      <div class="bg-gray-900 rounded-xl p-4 border border-gray-800 mb-6">
        <h4 class="text-xs text-gray-500 uppercase mb-3">Success Criteria</h4>
        ${s.success_criteria.map((c,i) => `
          <div class="flex items-start gap-2 mb-2">
            <span class="text-xs bg-gray-800 text-gray-400 rounded px-1.5 py-0.5 mt-0.5">${i+1}</span>
            <div>
              <span class="text-xs text-indigo-400 font-mono">${c.id}</span>
              <p class="text-sm text-gray-300">${esc(c.description)}</p>
            </div>
          </div>
        `).join('')}
      </div>
      <button onclick="deleteScenario('${s.name}')" class="text-xs text-red-500 hover:text-red-400">Delete scenario</button>
    </div>`;
}

async function deleteScenario(name) {
  if (!confirm('Delete scenario ' + name + '?')) return;
  await fetch(`${API}/api/scenarios/${name}`, {method:'DELETE'});
  navigate('scenarios');
}

// --- Create Scenario ---
function renderCreateScenario(el) {
  el.innerHTML = `
    <div class="fade-in max-w-2xl">
      <button onclick="navigate('scenarios')" class="text-sm text-gray-500 hover:text-white mb-4 inline-block">&larr; Back</button>
      <h2 class="text-2xl font-bold mb-6">New Scenario</h2>
      <form onsubmit="submitScenario(event)" class="space-y-4">
        <div>
          <label class="block text-sm text-gray-400 mb-1">Name (slug)</label>
          <input id="f-name" required class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-brand focus:outline-none" placeholder="my-scenario">
        </div>
        <div>
          <label class="block text-sm text-gray-400 mb-1">Description</label>
          <input id="f-desc" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-brand focus:outline-none" placeholder="Customer calling to...">
        </div>
        <div>
          <label class="block text-sm text-gray-400 mb-1">Goal</label>
          <input id="f-goal" required class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-brand focus:outline-none" placeholder="Successfully book an appointment">
        </div>
        <div>
          <label class="block text-sm text-gray-400 mb-1">Persona (system prompt)</label>
          <textarea id="f-persona" rows="6" required class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-brand focus:outline-none font-mono" placeholder="You are Sarah, a friendly customer calling to..."></textarea>
        </div>
        <div>
          <label class="block text-sm text-gray-400 mb-1">Max Duration (seconds)</label>
          <input id="f-dur" type="number" value="120" class="w-32 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-brand focus:outline-none">
        </div>
        <div>
          <label class="block text-sm text-gray-400 mb-1">Success Criteria (one per line)</label>
          <textarea id="f-criteria" rows="5" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-brand focus:outline-none font-mono" placeholder="agent greeted the caller professionally&#10;agent completed the request&#10;agent confirmed the outcome"></textarea>
        </div>
        <button type="submit" class="bg-brand hover:bg-indigo-600 text-white px-6 py-2 rounded-lg text-sm transition">Create Scenario</button>
        <p id="f-error" class="text-red-400 text-sm hidden"></p>
      </form>
    </div>`;
}

async function submitScenario(e) {
  e.preventDefault();
  const name = document.getElementById('f-name').value.trim();
  const criteria = document.getElementById('f-criteria').value.trim().split('\\n').filter(l => l.trim());
  const body = {
    name,
    description: document.getElementById('f-desc').value.trim(),
    goal: document.getElementById('f-goal').value.trim(),
    persona: document.getElementById('f-persona').value.trim(),
    max_duration_seconds: parseInt(document.getElementById('f-dur').value) || 120,
    success_criteria: criteria,
  };
  const res = await fetch(`${API}/api/scenarios`, {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
  });
  if (res.ok) { navigate('scenarios'); }
  else {
    const err = document.getElementById('f-error');
    err.textContent = await res.text();
    err.classList.remove('hidden');
  }
}

// --- Results Page ---
async function renderResults(el) {
  const res = await fetch(`${API}/api/results`);
  const results = await res.json();
  if (!results.length) {
    el.innerHTML = '<div class="fade-in"><h2 class="text-2xl font-bold mb-4">Results</h2><p class="text-gray-500">No results yet. Run a test call first.</p></div>';
    return;
  }
  el.innerHTML = `
    <div class="fade-in">
      <h2 class="text-2xl font-bold mb-6">Results</h2>
      <div class="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-gray-800/50 text-gray-400">
            <tr>
              <th class="text-left px-4 py-3">Timestamp</th>
              <th class="text-left px-4 py-3">Scenario</th>
              <th class="text-center px-4 py-3">Result</th>
              <th class="text-right px-4 py-3">Duration</th>
              <th class="text-right px-4 py-3">Turns</th>
            </tr>
          </thead>
          <tbody>
            ${results.map(r => `
              <tr onclick="navigate('result-detail','${r.id}')" class="border-t border-gray-800 hover:bg-gray-800/50 cursor-pointer transition">
                <td class="px-4 py-3 text-gray-300 font-mono text-xs">${r.id}</td>
                <td class="px-4 py-3">${r.scenario || '—'}</td>
                <td class="px-4 py-3 text-center">${r.overall === 'PASS' ? '<span class=\\"text-green-400\\">PASS</span>' : r.overall === 'FAIL' ? '<span class=\\"text-red-400\\">FAIL</span>' : '—'}</td>
                <td class="px-4 py-3 text-right text-gray-400">${r.duration_seconds || '—'}s</td>
                <td class="px-4 py-3 text-right text-gray-400">${r.transcript_turns || '—'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>`;
}

// --- Result Detail ---
async function renderResultDetail(el, id) {
  const res = await fetch(`${API}/api/results/${id}`);
  const data = await res.json();
  const meta = data.metadata || {};
  const ev = data.evaluation || {};
  const m = data.metrics || {};
  const tx = data.transcript || {};
  const lat = m.response_latency || {};
  const turns = tx.turns || [];

  el.innerHTML = `
    <div class="fade-in max-w-4xl">
      <button onclick="navigate('results')" class="text-sm text-gray-500 hover:text-white mb-4 inline-block">&larr; Back</button>
      <div class="flex items-center gap-4 mb-6">
        <h2 class="text-2xl font-bold">${id}</h2>
        ${ev.overall ? `<span class="px-3 py-1 rounded-full text-sm font-medium ${ev.overall === 'PASS' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}">${ev.overall}</span>` : ''}
      </div>

      <div class="grid grid-cols-4 gap-4 mb-6">
        <div class="bg-gray-900 rounded-xl p-4 border border-gray-800 text-center">
          <div class="text-2xl font-bold">${meta.duration_seconds || '—'}s</div>
          <div class="text-xs text-gray-500 mt-1">Duration</div>
        </div>
        <div class="bg-gray-900 rounded-xl p-4 border border-gray-800 text-center">
          <div class="text-2xl font-bold">${meta.transcript_turns || '—'}</div>
          <div class="text-xs text-gray-500 mt-1">Turns</div>
        </div>
        <div class="bg-gray-900 rounded-xl p-4 border border-gray-800 text-center">
          <div class="text-2xl font-bold">${lat.p50 || '—'}s</div>
          <div class="text-xs text-gray-500 mt-1">Latency p50</div>
        </div>
        <div class="bg-gray-900 rounded-xl p-4 border border-gray-800 text-center">
          <div class="text-2xl font-bold">${(m.interruptions||{}).count ?? '—'}</div>
          <div class="text-xs text-gray-500 mt-1">Interruptions</div>
        </div>
      </div>

      ${ev.criteria ? `
      <div class="bg-gray-900 rounded-xl border border-gray-800 p-5 mb-6">
        <h3 class="text-sm font-semibold text-gray-400 uppercase mb-3">Evaluation</h3>
        <p class="text-sm text-gray-300 mb-4">${ev.summary || ''}</p>
        ${ev.criteria.map(c => `
          <div class="flex items-start gap-3 mb-2">
            <span class="mt-0.5 px-2 py-0.5 rounded text-xs font-medium ${c.result==='PASS'?'bg-green-500/20 text-green-400':'bg-red-500/20 text-red-400'}">${c.result}</span>
            <div>
              <span class="text-xs font-mono text-indigo-400">${c.id}</span>
              <p class="text-sm text-gray-400">${esc(c.explanation)}</p>
            </div>
          </div>
        `).join('')}
      </div>` : ''}

      ${turns.length ? `
      <div class="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <h3 class="text-sm font-semibold text-gray-400 uppercase mb-3">Transcript</h3>
        <div class="space-y-2">
          ${turns.map(t => `
            <div class="flex gap-3">
              <span class="text-xs text-gray-600 w-12 text-right shrink-0 mt-0.5">${t.start_time}s</span>
              <span class="text-xs font-medium w-20 shrink-0 mt-0.5 ${t.speaker==='AGENT'?'text-blue-400':'text-green-400'}">${t.speaker}</span>
              <p class="text-sm text-gray-300">${esc(t.text)}</p>
            </div>
          `).join('')}
        </div>
      </div>` : ''}
    </div>`;
}

// Init
navigate('scenarios');
</script>
</body>
</html>
"""
