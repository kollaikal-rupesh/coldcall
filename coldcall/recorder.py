"""Audio recording and session management for ColdCall calls."""

import json
import logging
import struct
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

from pipecat.frames.frames import (
    AudioRawFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

log = logging.getLogger("coldcall")

RESULTS_DIR = Path("results")
SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2  # 16-bit PCM
NUM_CHANNELS = 1


class CallSession:
    """Manages a single call's recordings, transcript, and metadata."""

    def __init__(self, call_sid: str, scenario: str = "default"):
        self.call_sid = call_sid
        self.scenario = scenario
        self.start_time = datetime.now(timezone.utc)
        self.end_time: datetime | None = None

        # Create results directory: results/<ISO-timestamp>/
        ts = self.start_time.strftime("%Y-%m-%dT%H:%M:%S")
        self.output_dir = RESULTS_DIR / ts
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Raw PCM buffers
        self.agent_audio = bytearray()
        self.caller_audio = bytearray()

        # Structured transcript
        self.turns: list[dict] = []

        self._start_mono = time.monotonic()

        log.info(f"Session created: {self.output_dir}")

    def elapsed(self) -> float:
        """Seconds since call start."""
        return time.monotonic() - self._start_mono

    def add_agent_audio(self, audio: bytes):
        self.agent_audio.extend(audio)

    def add_caller_audio(self, audio: bytes):
        self.caller_audio.extend(audio)

    def add_turn(self, speaker: str, text: str, start_time: float, end_time: float):
        self.turns.append({
            "speaker": speaker,
            "text": text,
            "start_time": round(start_time, 2),
            "end_time": round(end_time, 2),
        })

    def save(self):
        """Write all recordings, transcript, and metadata to disk."""
        self.end_time = datetime.now(timezone.utc)
        duration = (self.end_time - self.start_time).total_seconds()

        # Save WAV files
        self._save_wav("agent_audio.wav", self.agent_audio)
        self._save_wav("caller_audio.wav", self.caller_audio)
        self._save_mixed_wav("mixed_audio.wav")

        # Save transcript
        transcript_path = self.output_dir / "transcript.json"
        transcript_path.write_text(json.dumps({"turns": self.turns}, indent=2))

        # Save metadata
        metadata = {
            "call_sid": self.call_sid,
            "scenario": self.scenario,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": round(duration, 1),
            "sample_rate": SAMPLE_RATE,
            "agent_audio_seconds": round(len(self.agent_audio) / (SAMPLE_RATE * SAMPLE_WIDTH), 1),
            "caller_audio_seconds": round(len(self.caller_audio) / (SAMPLE_RATE * SAMPLE_WIDTH), 1),
            "transcript_turns": len(self.turns),
        }
        metadata_path = self.output_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2))

        log.info(
            f"Session saved: {self.output_dir} "
            f"(duration={duration:.1f}s, turns={len(self.turns)})"
        )

        # Compute audio metrics (VAD-based)
        try:
            from coldcall.metrics import compute_metrics

            compute_metrics(self.output_dir)
        except Exception:
            log.exception("Failed to compute metrics")

        # Generate reports (after metrics + evaluation are written by the bot)
        # Reports are generated separately via generate_reports() after evaluation

    def _save_wav(self, filename: str, audio_data: bytes | bytearray):
        path = self.output_dir / filename
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(NUM_CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(bytes(audio_data))
        size_kb = len(audio_data) / 1024
        log.info(f"  Saved {filename} ({size_kb:.0f} KB)")

    def _save_mixed_wav(self, filename: str):
        """Mix agent and caller audio into a single mono WAV."""
        agent = self.agent_audio
        caller = self.caller_audio

        # Pad shorter buffer to match length
        max_len = max(len(agent), len(caller))
        agent_padded = bytes(agent) + b"\x00" * (max_len - len(agent))
        caller_padded = bytes(caller) + b"\x00" * (max_len - len(caller))

        # Mix: add samples and clamp to int16 range
        mixed = bytearray()
        for i in range(0, max_len, SAMPLE_WIDTH):
            a = struct.unpack_from("<h", agent_padded, i)[0] if i + 1 < max_len else 0
            c = struct.unpack_from("<h", caller_padded, i)[0] if i + 1 < max_len else 0
            m = max(-32768, min(32767, a + c))
            mixed.extend(struct.pack("<h", m))

        self._save_wav(filename, mixed)


class AudioCaptureProcessor(FrameProcessor):
    """Captures raw audio frames flowing through the pipeline into a CallSession."""

    def __init__(self, session: CallSession, channel: str):
        super().__init__()
        self._session = session
        self._channel = channel  # "agent" or "caller"

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, AudioRawFrame):
            if self._channel == "agent":
                self._session.add_agent_audio(frame.audio)
            else:
                self._session.add_caller_audio(frame.audio)

        await self.push_frame(frame, direction)


class AgentTranscriptProcessor(FrameProcessor):
    """Captures AGENT speech from STT TranscriptionFrames with start/end times.

    Deepgram sends interim results then a final TranscriptionFrame per utterance.
    We track when audio for the utterance started (via the audio buffer position)
    and when the final transcript arrives.
    """

    def __init__(self, session: CallSession):
        super().__init__()
        self._session = session
        self._utterance_start: float | None = None

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            end_time = self._session.elapsed()
            # Estimate start_time from audio buffer position minus a reasonable
            # utterance duration. The audio buffer length tells us total inbound
            # audio received; the STT result arrives after the speaker finishes.
            # We estimate utterance duration at ~0.08s per word.
            words = len(frame.text.split())
            estimated_duration = max(0.5, words * 0.08 * 5)  # rough: ~0.4s/word
            start_time = max(0.0, end_time - estimated_duration)

            self._session.add_turn("AGENT", frame.text, start_time, end_time)
            log.info(
                f"  AGENT   [{start_time:.1f}s - {end_time:.1f}s]: {frame.text}"
            )

        await self.push_frame(frame, direction)


class CallerTranscriptProcessor(FrameProcessor):
    """Captures COLDCALL (caller) speech from LLM TextFrames with start/end times.

    LLM streams tokens as TextFrames. We buffer until sentence boundaries,
    then record each sentence with its start/end time.
    """

    def __init__(self, session: CallSession):
        super().__init__()
        self._session = session
        self._buffer = ""
        self._turn_start: float | None = None

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TextFrame) and not isinstance(frame, TranscriptionFrame):
            if not self._buffer:
                self._turn_start = self._session.elapsed()

            self._buffer += frame.text

            # Flush complete sentences
            last_sep = -1
            for i, ch in enumerate(self._buffer):
                if ch in ".!?":
                    last_sep = i

            if last_sep >= 0:
                sentence = self._buffer[:last_sep + 1].strip()
                self._buffer = self._buffer[last_sep + 1:]
                if sentence:
                    end_time = self._session.elapsed()
                    start_time = self._turn_start if self._turn_start is not None else end_time
                    self._session.add_turn("COLDCALL", sentence, start_time, end_time)
                    log.info(
                        f"  COLDCALL [{start_time:.1f}s - {end_time:.1f}s]: {sentence}"
                    )
                    # Next sentence in same LLM response starts from here
                    self._turn_start = end_time

        await self.push_frame(frame, direction)

    def flush(self):
        """Flush any remaining buffered text as a final turn."""
        if self._buffer.strip():
            end_time = self._session.elapsed()
            start_time = self._turn_start if self._turn_start is not None else end_time
            self._session.add_turn("COLDCALL", self._buffer.strip(), start_time, end_time)
            log.info(
                f"  COLDCALL [{start_time:.1f}s - {end_time:.1f}s]: {self._buffer.strip()}"
            )
            self._buffer = ""
            self._turn_start = None
