"""WebSocket client transport for ColdCall.

Connects to a voice agent's WebSocket endpoint as a CLIENT,
sends/receives raw PCM audio. No Twilio, no server, no tunnel needed.

Supports multiple audio protocols:
- raw: binary PCM frames (16-bit, configurable sample rate)
- json: JSON messages with base64-encoded audio payload
"""

import asyncio
import base64
import json
import logging
import struct

import websockets

from pipecat.frames.frames import (
    AudioRawFrame,
    EndFrame,
    InputAudioRawFrame,
    StartFrame,
    CancelFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

log = logging.getLogger("coldcall")


class WebSocketClientInput(FrameProcessor):
    """Reads audio from a WebSocket connection and produces InputAudioRawFrame."""

    def __init__(self, ws, sample_rate: int = 16000, protocol: str = "raw"):
        super().__init__()
        self._ws = ws
        self._sample_rate = sample_rate
        self._protocol = protocol
        self._running = False

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            self._running = True
            asyncio.create_task(self._read_loop())

        elif isinstance(frame, (EndFrame, CancelFrame)):
            self._running = False

        await self.push_frame(frame, direction)

    async def _read_loop(self):
        """Read audio frames from the WebSocket."""
        try:
            async for message in self._ws:
                if not self._running:
                    break

                audio = self._decode(message)
                if audio:
                    frame = InputAudioRawFrame(
                        audio=audio,
                        sample_rate=self._sample_rate,
                        num_channels=1,
                    )
                    await self.push_frame(frame)
        except websockets.ConnectionClosed:
            log.info("Agent WebSocket disconnected")
        except Exception:
            log.exception("Error reading from agent WebSocket")
        finally:
            self._running = False
            await self.push_frame(EndFrame())

    def _decode(self, message) -> bytes | None:
        """Decode a WebSocket message into raw PCM bytes."""
        if self._protocol == "raw":
            if isinstance(message, bytes):
                return message
            return None

        if self._protocol == "json":
            try:
                data = json.loads(message)
                # Support common JSON audio formats
                payload = data.get("audio") or data.get("media", {}).get("payload") or data.get("data")
                if payload:
                    return base64.b64decode(payload)
            except (json.JSONDecodeError, KeyError):
                pass
            return None

        return message if isinstance(message, bytes) else None


class WebSocketClientOutput(FrameProcessor):
    """Sends audio frames to a WebSocket connection."""

    def __init__(self, ws, sample_rate: int = 16000, protocol: str = "raw"):
        super().__init__()
        self._ws = ws
        self._sample_rate = sample_rate
        self._protocol = protocol

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, AudioRawFrame):
            try:
                encoded = self._encode(frame.audio)
                await self._ws.send(encoded)
            except websockets.ConnectionClosed:
                pass
            except Exception:
                log.exception("Error sending to agent WebSocket")

        await self.push_frame(frame, direction)

    def _encode(self, audio: bytes) -> bytes | str:
        """Encode raw PCM to the WebSocket protocol format."""
        if self._protocol == "raw":
            return audio

        if self._protocol == "json":
            return json.dumps({
                "audio": base64.b64encode(audio).decode("ascii"),
                "sample_rate": self._sample_rate,
            })

        return audio


async def connect_to_agent(
    url: str,
    sample_rate: int = 16000,
    protocol: str = "raw",
    extra_headers: dict | None = None,
) -> tuple:
    """Connect to an agent's WebSocket and return (ws, input_processor, output_processor).

    Args:
        url: WebSocket URL (ws:// or wss://)
        sample_rate: Audio sample rate in Hz
        protocol: "raw" (binary PCM) or "json" (JSON with base64 audio)
        extra_headers: Optional headers for authentication etc.

    Returns:
        (websocket, input_processor, output_processor)
    """
    headers = extra_headers or {}

    log.info(f"Connecting to agent at {url} (protocol={protocol}, rate={sample_rate}Hz)")
    ws = await websockets.connect(url, additional_headers=headers)
    log.info("Connected to agent WebSocket")

    ws_input = WebSocketClientInput(ws, sample_rate=sample_rate, protocol=protocol)
    ws_output = WebSocketClientOutput(ws, sample_rate=sample_rate, protocol=protocol)

    return ws, ws_input, ws_output
