"""Pipecat voice bot pipeline — receives Twilio audio, runs STT -> LLM -> TTS."""

import os
import logging

from fastapi import WebSocket

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
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from coldcall.humanizer import HumanizerProcessor
from coldcall.noise import NoiseInjectorProcessor
from coldcall.recorder import (
    AgentTranscriptProcessor,
    AudioCaptureProcessor,
    CallerTranscriptProcessor,
    CallSession,
)
from coldcall.scenarios import Scenario

log = logging.getLogger("coldcall")

DEFAULT_SCENARIO = "dental-appointment"


async def run_bot(
    websocket: WebSocket,
    scenario: Scenario | None = None,
    on_call_complete: callable | None = None,
) -> dict | None:
    """Run the voice bot pipeline on an accepted Twilio WebSocket.

    Args:
        websocket: Accepted FastAPI WebSocket.
        scenario: Scenario config. Loads default if None.
        on_call_complete: Optional callback with (session_dir, evaluation_result).

    Returns:
        Evaluation result dict, or None on error.
    """
    if scenario is None:
        scenario = Scenario.from_yaml(DEFAULT_SCENARIO)

    evaluation_result = None

    _, call_data = await parse_telephony_websocket(websocket)
    call_id = call_data["call_id"]
    log.info(f"Call connected: stream={call_data['stream_id']} call={call_id}")
    log.info(f"Scenario: {scenario.name} — {scenario.description}")
    if scenario.humanize:
        log.info("  Humanizer: enabled")
    if scenario.noise_profile:
        log.info(f"  Noise: {scenario.noise_profile} (vol={scenario.noise_volume})")

    session = CallSession(call_sid=call_id, scenario=scenario.name)

    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_id,
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    missing_keys = []
    for key in ("DEEPGRAM_API_KEY", "OPENAI_API_KEY", "CARTESIA_API_KEY"):
        if not os.environ.get(key):
            missing_keys.append(key)
    if missing_keys:
        raise RuntimeError(f"Missing required API keys: {', '.join(missing_keys)}")

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

    # Audio capture
    agent_audio_capture = AudioCaptureProcessor(session, "agent")
    caller_audio_capture = AudioCaptureProcessor(session, "caller")

    # Transcript capture
    agent_transcript = AgentTranscriptProcessor(session)
    caller_transcript = CallerTranscriptProcessor(session)

    # Humanizer (between LLM and TTS)
    humanizer = HumanizerProcessor(enabled=scenario.humanize)

    # Noise injector (after TTS, before transport output)
    noise_injector = NoiseInjectorProcessor(
        profile=scenario.noise_profile,
        volume=scenario.noise_volume,
    )

    pipeline = Pipeline([
        transport.input(),
        agent_audio_capture,    # Capture agent audio (inbound)
        stt,
        agent_transcript,       # Log agent STT text
        user_aggregator,
        llm,
        humanizer,              # Fillers, corrections, pauses
        caller_transcript,      # Log bot LLM text (after humanization)
        tts,
        noise_injector,         # Mix background noise
        caller_audio_capture,   # Capture bot audio (outbound)
        transport.output(),
        assistant_aggregator,
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        log.info("Client connected — bot will greet caller")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        log.info("Client disconnected")
        caller_transcript.flush()
        session.save()

        try:
            from coldcall.judge import evaluate_session
            nonlocal evaluation_result
            evaluation_result = evaluate_session(session.output_dir, scenario)
        except Exception:
            log.exception("Failed to run evaluation")

        try:
            from coldcall.report import generate_reports
            generate_reports(session.output_dir)
        except Exception:
            log.exception("Failed to generate reports")

        if on_call_complete:
            try:
                on_call_complete(session.output_dir, evaluation_result)
            except Exception:
                log.exception("on_call_complete callback error")

        await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
    return evaluation_result
