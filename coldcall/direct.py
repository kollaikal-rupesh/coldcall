"""Direct WebSocket test runner — connects to an agent without Twilio.

Usage:
    coldcall test ws://agent:8080/ws --scenario dental-appointment

Connects directly to the agent's WebSocket endpoint, runs the full
STT → LLM → TTS pipeline, records everything, and evaluates.
No Twilio, no phone number, no tunnel, no per-minute costs.
"""

import asyncio
import logging
import os

from coldcall.humanizer import HumanizerProcessor
from coldcall.noise import NoiseInjectorProcessor
from coldcall.recorder import (
    AgentTranscriptProcessor,
    AudioCaptureProcessor,
    CallerTranscriptProcessor,
    CallSession,
)
from coldcall.scenarios import Scenario
from coldcall.transport import connect_to_agent

log = logging.getLogger("coldcall")


async def run_direct_test(
    url: str,
    scenario: Scenario,
    sample_rate: int = 16000,
    protocol: str = "raw",
) -> dict | None:
    """Connect to an agent's WebSocket and run a test scenario.

    Args:
        url: Agent's WebSocket URL (ws:// or wss://)
        scenario: Scenario configuration
        sample_rate: Audio sample rate for the connection
        protocol: "raw" (binary PCM) or "json" (JSON with base64 audio)

    Returns:
        Evaluation result dict, or None.
    """
    # Lazy imports to avoid loading pipecat on every CLI invocation
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.frames.frames import EndFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )
    from pipecat.services.cartesia.tts import CartesiaTTSService
    from pipecat.services.deepgram.stt import DeepgramSTTService
    from pipecat.services.openai.llm import OpenAILLMService

    missing_keys = []
    for key in ("DEEPGRAM_API_KEY", "OPENAI_API_KEY", "CARTESIA_API_KEY"):
        if not os.environ.get(key):
            missing_keys.append(key)
    if missing_keys:
        raise RuntimeError(f"Missing required API keys: {', '.join(missing_keys)}")

    log.info(f"Scenario: {scenario.name} — {scenario.description}")
    log.info(f"  Agent URL: {url}")
    log.info(f"  Protocol: {protocol}, Sample rate: {sample_rate}Hz")
    if scenario.humanize:
        log.info("  Humanizer: enabled")
    if scenario.noise_profile:
        log.info(f"  Noise: {scenario.noise_profile} (vol={scenario.noise_volume})")

    # Connect to the agent
    ws, ws_input, ws_output = await connect_to_agent(
        url, sample_rate=sample_rate, protocol=protocol,
    )

    session = CallSession(call_sid=f"direct-{url}", scenario=scenario.name)
    evaluation_result = None

    # Services
    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])

    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAILLMService.Settings(model="gpt-4o-mini"),
    )

    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        voice_id=scenario.persona.voice_id,
    )

    context = LLMContext(
        messages=[{"role": "system", "content": scenario.persona.system_prompt}],
    )

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    # Processors
    agent_audio_capture = AudioCaptureProcessor(session, "agent")
    caller_audio_capture = AudioCaptureProcessor(session, "caller")
    agent_transcript = AgentTranscriptProcessor(session)
    caller_transcript = CallerTranscriptProcessor(session)
    humanizer = HumanizerProcessor(enabled=scenario.humanize)
    noise_injector = NoiseInjectorProcessor(
        profile=scenario.noise_profile,
        volume=scenario.noise_volume,
    )

    pipeline = Pipeline([
        ws_input,                   # Receive agent audio from WebSocket
        agent_audio_capture,        # Record agent audio
        stt,                        # Speech-to-text
        agent_transcript,           # Log agent words
        user_aggregator,
        llm,                        # Generate response
        humanizer,                  # Add fillers, pauses
        caller_transcript,          # Log our words
        tts,                        # Text-to-speech
        noise_injector,             # Add background noise
        caller_audio_capture,       # Record our audio
        ws_output,                  # Send audio back to agent
        assistant_aggregator,
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=sample_rate,
            audio_out_sample_rate=sample_rate,
            enable_metrics=True,
        ),
    )

    runner = PipelineRunner(handle_sigint=True)

    try:
        await runner.run(task)
    except KeyboardInterrupt:
        log.info("Test interrupted")
    finally:
        # Save everything
        caller_transcript.flush()
        session.save()

        try:
            from coldcall.judge import evaluate_session
            evaluation_result = evaluate_session(session.output_dir, scenario)
        except Exception:
            log.exception("Failed to run evaluation")

        try:
            from coldcall.report import generate_reports
            generate_reports(session.output_dir)
        except Exception:
            log.exception("Failed to generate reports")

        try:
            await ws.close()
        except Exception:
            pass

    return evaluation_result
