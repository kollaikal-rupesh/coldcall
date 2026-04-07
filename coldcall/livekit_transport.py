"""LiveKit transport for ColdCall.

Joins a LiveKit room as a participant, sends TTS audio as a track,
and receives the agent's audio track for STT processing.

Usage:
    coldcall test lk://room-name --scenario dental-appointment
"""

import asyncio
import logging
import os
import struct

from livekit import rtc, api

log = logging.getLogger("coldcall")

SAMPLE_RATE = 24000
NUM_CHANNELS = 1
SAMPLES_PER_CHANNEL = 480  # 20ms at 24kHz


async def create_room_and_token(room_name: str) -> tuple[str, str]:
    """Create a LiveKit room and generate a participant token.

    Returns (livekit_url, token).
    """
    lk_url = os.environ.get("LIVEKIT_URL", "")
    lk_api_key = os.environ.get("LIVEKIT_API_KEY", "")
    lk_api_secret = os.environ.get("LIVEKIT_API_SECRET", "")

    if not lk_url or not lk_api_key or not lk_api_secret:
        raise RuntimeError(
            "Missing LiveKit credentials. Set LIVEKIT_URL, LIVEKIT_API_KEY, "
            "and LIVEKIT_API_SECRET in coldcall.yaml or environment."
        )

    # Generate a token for ColdCall to join as a participant
    token = (
        api.AccessToken(lk_api_key, lk_api_secret)
        .with_identity("coldcall-tester")
        .with_name("ColdCall")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
            )
        )
        .to_jwt()
    )

    return lk_url, token


async def run_livekit_test(
    room_name: str,
    scenario,
    sample_rate: int = SAMPLE_RATE,
) -> dict | None:
    """Connect to a LiveKit room and run a test scenario against the agent.

    Args:
        room_name: LiveKit room name to join.
        scenario: Scenario configuration.
        sample_rate: Audio sample rate (default 24kHz for LiveKit).

    Returns:
        Evaluation result dict, or None.
    """
    from coldcall.humanizer import HumanizerProcessor
    from coldcall.recorder import (
        AgentTranscriptProcessor,
        CallerTranscriptProcessor,
        CallSession,
    )

    # Lazy imports for Pipecat
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.frames.frames import EndFrame, InputAudioRawFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
    from pipecat.frames.frames import AudioRawFrame
    from pipecat.services.cartesia.tts import CartesiaTTSService
    from pipecat.services.deepgram.stt import DeepgramSTTService
    from pipecat.services.openai.llm import OpenAILLMService

    missing_keys = []
    for key in ("DEEPGRAM_API_KEY", "OPENAI_API_KEY", "CARTESIA_API_KEY"):
        if not os.environ.get(key):
            missing_keys.append(key)
    if missing_keys:
        raise RuntimeError(f"Missing required API keys: {', '.join(missing_keys)}")

    lk_url, token = await create_room_and_token(room_name)

    log.info(f"Connecting to LiveKit room: {room_name}")
    log.info(f"  URL: {lk_url}")
    log.info(f"  Scenario: {scenario.name}")

    session = CallSession(call_sid=f"livekit-{room_name}", scenario=scenario.name)
    evaluation_result = None

    # Connect to LiveKit room
    room = rtc.Room()

    # Audio source for publishing our TTS audio
    audio_source = rtc.AudioSource(sample_rate, NUM_CHANNELS)

    # Collect agent audio for processing
    agent_audio_queue = asyncio.Queue()

    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            log.info(f"Subscribed to agent audio: {participant.identity}")
            audio_stream = rtc.AudioStream(track)

            async def _read_audio():
                async for event in audio_stream:
                    frame = event.frame
                    # Convert to raw PCM bytes
                    pcm_data = frame.data.tobytes()
                    await agent_audio_queue.put(pcm_data)

            asyncio.create_task(_read_audio())

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        log.info(f"Participant disconnected: {participant.identity}")
        agent_audio_queue.put_nowait(None)  # Signal end

    await room.connect(lk_url, token)
    log.info("Connected to LiveKit room")

    # Publish our audio track
    local_track = rtc.LocalAudioTrack.create_audio_track("coldcall-audio", audio_source)
    await room.local_participant.publish_track(local_track)
    log.info("Published audio track")

    # Build a simple pipeline manually (not using Pipecat transport since
    # LiveKit has its own audio I/O)
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

    agent_transcript = AgentTranscriptProcessor(session)
    caller_transcript = CallerTranscriptProcessor(session)
    humanizer = HumanizerProcessor(enabled=scenario.humanize)

    # Output processor that sends audio to LiveKit
    class LiveKitOutput(FrameProcessor):
        async def process_frame(self, frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            if isinstance(frame, AudioRawFrame):
                # Convert PCM bytes to LiveKit AudioFrame
                pcm_int16 = frame.audio
                samples = len(pcm_int16) // 2
                lk_frame = rtc.AudioFrame(
                    data=pcm_int16,
                    sample_rate=frame.sample_rate,
                    num_channels=1,
                    samples_per_channel=samples,
                )
                await audio_source.capture_frame(lk_frame)
                session.add_caller_audio(pcm_int16)
            await self.push_frame(frame, direction)

    # Input processor that reads from the agent audio queue
    class LiveKitInput(FrameProcessor):
        def __init__(self):
            super().__init__()
            self._running = False

        async def process_frame(self, frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            from pipecat.frames.frames import StartFrame
            if isinstance(frame, StartFrame) and not self._running:
                self._running = True
                asyncio.create_task(self._read_loop())
            await self.push_frame(frame, direction)

        async def _read_loop(self):
            while self._running:
                pcm = await agent_audio_queue.get()
                if pcm is None:
                    self._running = False
                    await self.push_frame(EndFrame())
                    break
                session.add_agent_audio(pcm)
                frame = InputAudioRawFrame(
                    audio=pcm,
                    sample_rate=sample_rate,
                    num_channels=1,
                )
                await self.push_frame(frame)

    lk_input = LiveKitInput()
    lk_output = LiveKitOutput()

    pipeline = Pipeline([
        lk_input,
        stt,
        agent_transcript,
        user_aggregator,
        llm,
        humanizer,
        caller_transcript,
        tts,
        lk_output,
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

        await room.disconnect()

    return evaluation_result
