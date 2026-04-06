"""Background noise injection for ColdCall.

Mixes ambient noise into the caller's outgoing audio to simulate
realistic phone call environments.
"""

import logging
import math
import random
import struct
import wave
from pathlib import Path

import numpy as np
from pipecat.frames.frames import AudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

log = logging.getLogger("coldcall")

NOISE_DIR = Path(__file__).parent / "noise_samples"
SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2  # 16-bit PCM

# How long each generated noise loop is (seconds)
NOISE_LOOP_DURATION = 10


def _ensure_noise_samples():
    """Generate noise sample WAV files if they don't exist."""
    NOISE_DIR.mkdir(parents=True, exist_ok=True)
    profiles = {
        "cafe": _generate_cafe_noise,
        "street": _generate_street_noise,
        "office": _generate_office_noise,
        "car": _generate_car_noise,
        "wind": _generate_wind_noise,
    }
    for name, gen_fn in profiles.items():
        path = NOISE_DIR / f"{name}.wav"
        if not path.exists():
            samples = gen_fn(NOISE_LOOP_DURATION, SAMPLE_RATE)
            _save_wav(path, samples, SAMPLE_RATE)
            log.info(f"Generated noise sample: {path}")


def _save_wav(path: Path, samples: np.ndarray, sample_rate: int):
    """Save float32 samples as 16-bit WAV."""
    # Normalize to [-1, 1] then scale to int16
    peak = np.max(np.abs(samples))
    if peak > 0:
        samples = samples / peak
    pcm = (samples * 32000).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def _generate_cafe_noise(duration: float, sr: int) -> np.ndarray:
    """Cafe ambiance: pink noise + occasional clinks/murmur."""
    n = int(sr * duration)
    # Pink noise (1/f)
    white = np.random.randn(n)
    # Simple pink noise approximation via cumulative filter
    pink = np.zeros(n)
    b = [0.049922035, -0.095993537, 0.050612699, -0.004709510]
    a = [1.0, -2.494956002, 2.017265875, -0.522189400]
    from scipy.signal import lfilter
    pink = lfilter(b, a, white)
    # Add occasional clinking sounds
    for _ in range(int(duration * 2)):
        pos = random.randint(0, n - sr // 4)
        clink_len = random.randint(sr // 20, sr // 10)
        freq = random.uniform(2000, 4000)
        t = np.arange(clink_len) / sr
        clink = 0.3 * np.sin(2 * math.pi * freq * t) * np.exp(-t * 30)
        pink[pos:pos + clink_len] += clink[:min(clink_len, n - pos)]
    return pink


def _generate_street_noise(duration: float, sr: int) -> np.ndarray:
    """Street ambiance: brown noise + occasional car pass-bys."""
    n = int(sr * duration)
    # Brown noise (random walk)
    white = np.random.randn(n)
    brown = np.cumsum(white)
    brown = brown / np.max(np.abs(brown))
    # Low-pass to remove high frequencies
    from scipy.signal import butter, lfilter
    b, a = butter(4, 500 / (sr / 2), btype='low')
    brown = lfilter(b, a, brown)
    # Add car pass-by sounds (low rumble that swells and fades)
    for _ in range(int(duration / 3)):
        pos = random.randint(0, max(1, n - sr * 2))
        car_len = random.randint(sr, sr * 2)
        t = np.arange(car_len) / sr
        envelope = np.sin(math.pi * t / t[-1]) ** 2
        car = 0.5 * np.random.randn(car_len)
        b2, a2 = butter(2, 200 / (sr / 2), btype='low')
        car = lfilter(b2, a2, car) * envelope
        end = min(pos + car_len, n)
        brown[pos:end] += car[:end - pos]
    return brown


def _generate_office_noise(duration: float, sr: int) -> np.ndarray:
    """Office ambiance: very quiet white noise + HVAC hum."""
    n = int(sr * duration)
    # Quiet broadband noise
    noise = np.random.randn(n) * 0.1
    # HVAC hum at ~120Hz
    t = np.arange(n) / sr
    hum = 0.15 * np.sin(2 * math.pi * 120 * t)
    hum += 0.05 * np.sin(2 * math.pi * 240 * t)
    return noise + hum


def _generate_car_noise(duration: float, sr: int) -> np.ndarray:
    """Car interior: low-frequency engine rumble + road noise."""
    n = int(sr * duration)
    t = np.arange(n) / sr
    # Engine rumble (low freq with harmonics)
    rumble = 0.4 * np.sin(2 * math.pi * 40 * t + 0.5 * np.sin(2 * math.pi * 2 * t))
    rumble += 0.2 * np.sin(2 * math.pi * 80 * t)
    rumble += 0.1 * np.sin(2 * math.pi * 120 * t)
    # Road noise (filtered noise)
    road = np.random.randn(n) * 0.2
    from scipy.signal import butter, lfilter
    b, a = butter(3, 300 / (sr / 2), btype='low')
    road = lfilter(b, a, road)
    return rumble + road


def _generate_wind_noise(duration: float, sr: int) -> np.ndarray:
    """Wind noise: filtered noise with gusting envelope."""
    n = int(sr * duration)
    t = np.arange(n) / sr
    noise = np.random.randn(n)
    # Band-pass filter to wind frequencies
    from scipy.signal import butter, lfilter
    b, a = butter(3, [50 / (sr / 2), 800 / (sr / 2)], btype='band')
    wind = lfilter(b, a, noise)
    # Gusting envelope: slow modulation
    gust = 0.5 + 0.5 * np.sin(2 * math.pi * 0.3 * t + random.uniform(0, 2 * math.pi))
    gust *= 0.5 + 0.5 * np.sin(2 * math.pi * 0.1 * t)
    return wind * gust


class NoiseInjectorProcessor(FrameProcessor):
    """Mixes background noise into outgoing audio frames.

    Place after TTS and before transport.output() in the pipeline.
    """

    def __init__(self, profile: str = "", volume: float = 0.15):
        super().__init__()
        self._profile = profile
        self._volume = volume
        self._noise_pcm: bytes | None = None
        self._noise_pos = 0
        self._loaded = False

    def _load_noise(self):
        """Load noise sample on first use."""
        if self._loaded or not self._profile:
            return
        self._loaded = True

        _ensure_noise_samples()
        path = NOISE_DIR / f"{self._profile}.wav"
        if not path.exists():
            log.warning(f"Noise profile not found: {self._profile}")
            return

        with wave.open(str(path), "rb") as wf:
            self._noise_pcm = wf.readframes(wf.getnframes())

        log.info(f"Loaded noise profile: {self._profile} ({len(self._noise_pcm)} bytes)")

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if not self._profile or not isinstance(frame, AudioRawFrame):
            await self.push_frame(frame, direction)
            return

        self._load_noise()

        if not self._noise_pcm:
            await self.push_frame(frame, direction)
            return

        # Mix noise into the audio frame
        audio = frame.audio
        mixed = self._mix(audio)

        # Create a new frame with the mixed audio
        new_frame = AudioRawFrame(
            audio=mixed,
            sample_rate=frame.sample_rate,
            num_channels=frame.num_channels,
        )
        await self.push_frame(new_frame, direction)

    def _mix(self, audio: bytes) -> bytes:
        """Mix noise into audio at the configured volume."""
        audio_len = len(audio)
        noise_len = len(self._noise_pcm)

        mixed = bytearray()
        for i in range(0, audio_len, SAMPLE_WIDTH):
            if i + 1 >= audio_len:
                break

            # Audio sample
            a = struct.unpack_from("<h", audio, i)[0]

            # Noise sample (loop)
            noise_idx = self._noise_pos % noise_len
            if noise_idx + 1 < noise_len:
                n = struct.unpack_from("<h", self._noise_pcm, noise_idx)[0]
            else:
                n = 0
            self._noise_pos = (self._noise_pos + SAMPLE_WIDTH) % noise_len

            # Mix: audio + noise * volume, clamp to int16
            mixed_val = int(a + n * self._volume)
            mixed_val = max(-32768, min(32767, mixed_val))
            mixed.extend(struct.pack("<h", mixed_val))

        return bytes(mixed)


def available_profiles() -> list[str]:
    """List available noise profile names."""
    return ["cafe", "street", "office", "car", "wind"]
