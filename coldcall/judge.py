"""LLM-as-judge evaluation of voice agent transcripts."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from coldcall.scenarios import Scenario

log = logging.getLogger("coldcall")

JUDGE_MODEL = "gpt-4o-mini"

JUDGE_PROMPT = """\
You are evaluating a voice agent's performance on a phone call.

SCENARIO: {description}
GOAL: {goal}

SUCCESS CRITERIA:
{criteria}

TRANSCRIPT:
{transcript}

Evaluate the AGENT's performance against each success criterion.

Respond in this exact JSON format (no markdown, no code fences):
{{
  "criteria": [
    {{
      "id": "<criterion_id>",
      "result": "PASS" or "FAIL",
      "explanation": "<brief explanation>"
    }}
  ],
  "overall": "PASS" or "FAIL",
  "summary": "<one-sentence overall assessment>"
}}

Rules:
- overall is PASS only if ALL criteria pass
- Be strict: the criterion must be clearly met in the transcript
- If the transcript is too short or the call ended early, FAIL unmet criteria
"""


def format_transcript(turns: list[dict]) -> str:
    """Format transcript turns into readable text for the judge."""
    lines = []
    for turn in turns:
        speaker = turn["speaker"]
        text = turn["text"]
        t = turn.get("start_time", "?")
        lines.append(f"[{t}s] {speaker}: {text}")
    return "\n".join(lines)


def evaluate(
    scenario: Scenario,
    transcript_turns: list[dict],
    model: str = JUDGE_MODEL,
) -> dict:
    """Send transcript to LLM judge and get per-criterion evaluation.

    Returns the evaluation dict with criteria results and overall PASS/FAIL.
    """
    transcript_text = format_transcript(transcript_turns)

    prompt = JUDGE_PROMPT.format(
        description=scenario.description,
        goal=scenario.goal,
        criteria=scenario.criteria_text(),
        transcript=transcript_text,
    )

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    result = json.loads(raw)

    # Add metadata
    result["model"] = model
    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    result["scenario"] = scenario.name
    result["transcript_turns"] = len(transcript_turns)

    return result


def evaluate_session(session_dir: Path, scenario: Scenario) -> dict:
    """Evaluate a completed call session.

    Reads transcript.json from the session dir, runs the judge,
    and saves evaluation.json.
    """
    transcript_path = session_dir / "transcript.json"
    if not transcript_path.exists():
        raise FileNotFoundError(f"No transcript.json in {session_dir}")

    transcript_data = json.loads(transcript_path.read_text())
    turns = transcript_data.get("turns", [])

    if not turns:
        log.warning(f"Empty transcript in {session_dir}, skipping evaluation")
        return {"overall": "FAIL", "summary": "No transcript data", "criteria": []}

    log.info(f"Evaluating {session_dir} against scenario '{scenario.name}'...")

    result = evaluate(scenario, turns)

    # Save
    eval_path = session_dir / "evaluation.json"
    eval_path.write_text(json.dumps(result, indent=2))

    # Log summary
    passed = sum(1 for c in result.get("criteria", []) if c.get("result") == "PASS")
    total = len(result.get("criteria", []))
    overall = result.get("overall", "UNKNOWN")

    log.info(
        f"  Evaluation: {overall} ({passed}/{total} criteria passed)"
    )
    log.info(f"  Summary: {result.get('summary', 'N/A')}")
    for c in result.get("criteria", []):
        status = "PASS" if c["result"] == "PASS" else "FAIL"
        log.info(f"    [{status}] {c['id']}: {c['explanation']}")

    return result
