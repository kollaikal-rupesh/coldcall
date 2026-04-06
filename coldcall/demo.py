"""Demo mode — two LLMs have a phone conversation, no audio APIs needed.

Runs a full scenario with just OpenAI: one LLM plays the ColdCall persona,
another plays a simple voice agent. Text only, no STT/TTS, no Twilio.
Produces transcript, evaluation, and reports — same output as a real call.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from coldcall.scenarios import Scenario

log = logging.getLogger("coldcall")

RESULTS_DIR = Path("results")

AGENT_SYSTEM_PROMPT = """\
You are a helpful customer service agent answering a phone call. \
Be professional, friendly, and efficient. Ask for information you need \
to help the caller. Keep responses brief — this is a phone call, not an email. \
One or two sentences at a time. When you have all the information needed, \
confirm the details and wrap up the call.\
"""

MAX_TURNS = 20


def run_demo(
    scenario: Scenario,
    agent_prompt: str = AGENT_SYSTEM_PROMPT,
    model: str = "gpt-4o-mini",
) -> dict | None:
    """Run a text-only demo conversation between two LLMs.

    Args:
        scenario: The test scenario (provides the caller persona).
        agent_prompt: System prompt for the agent side.
        model: OpenAI model to use for both sides.

    Returns:
        Evaluation result dict.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required for demo mode.\n"
            "  export OPENAI_API_KEY=sk-...\n"
            "  Or add it to coldcall.yaml under openai.api_key"
        )

    client = OpenAI(api_key=api_key)
    start_time = datetime.now(timezone.utc)
    start_mono = time.monotonic()

    # Conversation state for both sides
    caller_messages = [
        {"role": "system", "content": scenario.persona.system_prompt},
        {"role": "user", "content": "The phone is ringing and someone answers. Start the conversation."},
    ]
    agent_messages = [
        {"role": "system", "content": agent_prompt},
    ]

    turns = []

    log.info(f"Demo: {scenario.name}")
    log.info(f"  Caller persona: {scenario.persona.name}")
    log.info(f"  Agent: generic customer service")
    log.info(f"  Model: {model}")
    log.info("")

    # Agent speaks first (greeting)
    agent_greeting = _chat(client, agent_messages + [
        {"role": "user", "content": "A customer is calling. Answer the phone with a greeting."}
    ], model)

    elapsed = time.monotonic() - start_mono
    turns.append({"speaker": "AGENT", "text": agent_greeting, "start_time": round(elapsed, 2), "end_time": round(elapsed + 0.5, 2)})
    agent_messages.append({"role": "assistant", "content": agent_greeting})
    log.info(f"  AGENT:    {agent_greeting}")

    # Caller responds to the greeting
    caller_messages.append({"role": "user", "content": f"The agent says: \"{agent_greeting}\""})

    for turn_num in range(MAX_TURNS):
        # Caller speaks
        caller_text = _chat(client, caller_messages, model)
        elapsed = time.monotonic() - start_mono
        turns.append({"speaker": "COLDCALL", "text": caller_text, "start_time": round(elapsed, 2), "end_time": round(elapsed + 0.5, 2)})
        caller_messages.append({"role": "assistant", "content": caller_text})
        log.info(f"  COLDCALL: {caller_text}")

        # Check if caller is ending the call
        if _is_goodbye(caller_text):
            break

        # Agent responds
        agent_messages.append({"role": "user", "content": caller_text})
        agent_text = _chat(client, agent_messages, model)
        elapsed = time.monotonic() - start_mono
        turns.append({"speaker": "AGENT", "text": agent_text, "start_time": round(elapsed, 2), "end_time": round(elapsed + 0.5, 2)})
        agent_messages.append({"role": "assistant", "content": agent_text})
        log.info(f"  AGENT:    {agent_text}")

        # Check if agent is ending the call
        if _is_goodbye(agent_text):
            break

        # Feed agent response back to caller
        caller_messages.append({"role": "user", "content": f"The agent says: \"{agent_text}\""})

    # Save results
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    ts = start_time.strftime("%Y-%m-%dT%H:%M:%S")
    output_dir = RESULTS_DIR / ts
    output_dir.mkdir(parents=True, exist_ok=True)

    # Transcript
    (output_dir / "transcript.json").write_text(json.dumps({"turns": turns}, indent=2))

    # Metadata
    metadata = {
        "call_sid": f"demo-{ts}",
        "scenario": scenario.name,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": round(duration, 1),
        "transcript_turns": len(turns),
        "mode": "demo",
        "model": model,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    log.info(f"\nSession saved: {output_dir} ({duration:.1f}s, {len(turns)} turns)")

    # Evaluate
    evaluation_result = None
    try:
        from coldcall.judge import evaluate_session
        evaluation_result = evaluate_session(output_dir, scenario)
    except Exception:
        log.exception("Failed to run evaluation")

    # Generate reports
    try:
        from coldcall.report import generate_reports
        generate_reports(output_dir)
    except Exception:
        log.exception("Failed to generate reports")

    return evaluation_result


def _chat(client: OpenAI, messages: list, model: str) -> str:
    """Single LLM completion."""
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
        max_tokens=150,
    )
    return resp.choices[0].message.content.strip()


def _is_goodbye(text: str) -> bool:
    """Check if the text indicates the conversation is ending."""
    lower = text.lower()
    endings = ["goodbye", "bye bye", "have a great day", "have a good day",
               "take care", "thanks, bye", "thank you, bye", "talk to you later"]
    return any(e in lower for e in endings)
