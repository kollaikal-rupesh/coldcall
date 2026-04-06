"""Audio metrics computation for ColdCall calls.

Computes response latency, interruption count, silence gaps, and turn stats
from recorded audio using Silero VAD for speech activity detection.
"""

import json
import logging
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger("coldcall")

# VAD configuration
VAD_CONFIDENCE_THRESHOLD = 0.5
# Merge speech segments closer than this (seconds) to avoid micro-splits
MERGE_GAP = 0.15
# Minimum silence gap to report (seconds)
SILENCE_GAP_THRESHOLD = 2.0


def _load_wav_pcm(path: Path) -> tuple[bytes, int]:
    """Load a WAV file and return (pcm_bytes, sample_rate)."""
    with wave.open(str(path), "rb") as wf:
        sample_rate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    return pcm, sample_rate


def compute_vad_timeline(
    pcm_bytes: bytes, sample_rate: int
) -> list[tuple[float, float]]:
    """Run Silero VAD on PCM audio and return speech segments as (start, end) pairs.

    Args:
        pcm_bytes: 16-bit signed PCM audio bytes
        sample_rate: Audio sample rate (8000 or 16000)

    Returns:
        List of (start_seconds, end_seconds) speech segments
    """
    from pipecat.audio.vad.silero import SileroVADAnalyzer

    vad = SileroVADAnalyzer(sample_rate=sample_rate)
    chunk_frames = vad.num_frames_required()
    chunk_bytes = chunk_frames * 2  # 16-bit = 2 bytes per sample
    chunk_duration = chunk_frames / sample_rate

    total_bytes = len(pcm_bytes)
    speech_active = False
    segments: list[tuple[float, float]] = []
    seg_start = 0.0

    offset = 0
    chunk_idx = 0
    while offset + chunk_bytes <= total_bytes:
        chunk = pcm_bytes[offset : offset + chunk_bytes]
        confidence = float(vad.voice_confidence(chunk))
        t = chunk_idx * chunk_duration

        if confidence >= VAD_CONFIDENCE_THRESHOLD and not speech_active:
            speech_active = True
            seg_start = t
        elif confidence < VAD_CONFIDENCE_THRESHOLD and speech_active:
            speech_active = False
            segments.append((seg_start, t))

        offset += chunk_bytes
        chunk_idx += 1

    # Close any open segment
    if speech_active:
        segments.append((seg_start, chunk_idx * chunk_duration))

    # Merge segments separated by less than MERGE_GAP
    merged: list[tuple[float, float]] = []
    for seg in segments:
        if merged and seg[0] - merged[-1][1] < MERGE_GAP:
            merged[-1] = (merged[-1][0], seg[1])
        else:
            merged.append(seg)

    return merged


def compute_response_latencies(
    agent_segments: list[tuple[float, float]],
    caller_segments: list[tuple[float, float]],
) -> list[float]:
    """Compute response latency for each agent turn.

    Latency = agent_speech_start - preceding_coldcall_speech_end

    Only counts cases where the agent responds AFTER ColdCall finishes
    (i.e. no overlap / interruption).
    """
    latencies = []

    for agent_start, _ in agent_segments:
        # Find the most recent caller segment that ended before this agent segment started
        preceding_end = None
        for _, caller_end in caller_segments:
            if caller_end <= agent_start:
                preceding_end = caller_end
            else:
                break

        if preceding_end is not None:
            latency = agent_start - preceding_end
            if latency >= 0:
                latencies.append(round(latency, 3))

    return latencies


def compute_interruptions(
    agent_segments: list[tuple[float, float]],
    caller_segments: list[tuple[float, float]],
) -> list[dict]:
    """Detect interruptions: agent starts speaking while ColdCall is still speaking."""
    interruptions = []

    for agent_start, agent_end in agent_segments:
        for caller_start, caller_end in caller_segments:
            # Agent starts during a ColdCall segment
            if caller_start < agent_start < caller_end:
                overlap_end = min(agent_end, caller_end)
                interruptions.append({
                    "time": round(agent_start, 2),
                    "overlap_seconds": round(overlap_end - agent_start, 2),
                })
                break

    return interruptions


def compute_silence_gaps(
    agent_segments: list[tuple[float, float]],
    caller_segments: list[tuple[float, float]],
    total_duration: float,
) -> list[dict]:
    """Find silence gaps > SILENCE_GAP_THRESHOLD where neither party is speaking."""
    # Merge all speech into a unified timeline
    all_segments = sorted(agent_segments + caller_segments, key=lambda s: s[0])
    merged: list[tuple[float, float]] = []
    for seg in all_segments:
        if merged and seg[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], seg[1]))
        else:
            merged.append(seg)

    # Find gaps between merged speech segments
    gaps = []
    prev_end = 0.0
    for start, end in merged:
        gap = start - prev_end
        if gap >= SILENCE_GAP_THRESHOLD:
            gaps.append({
                "start": round(prev_end, 2),
                "end": round(start, 2),
                "duration": round(gap, 2),
            })
        prev_end = end

    # Check trailing silence
    trailing = total_duration - prev_end
    if trailing >= SILENCE_GAP_THRESHOLD:
        gaps.append({
            "start": round(prev_end, 2),
            "end": round(total_duration, 2),
            "duration": round(trailing, 2),
        })

    return gaps


def percentile(values: list[float], p: float) -> float | None:
    """Compute percentile using numpy. Returns None if empty."""
    if not values:
        return None
    return round(float(np.percentile(values, p)), 3)


def compute_metrics(session_dir: Path) -> dict:
    """Compute all audio metrics for a call session.

    Reads agent_audio.wav and caller_audio.wav, runs Silero VAD, and computes:
    - Response latency (p50, p95, p99)
    - Interruption count
    - Silence gaps (> 2s)
    - Call duration
    - Turn count

    Saves metrics.json to session_dir.
    """
    agent_wav = session_dir / "agent_audio.wav"
    caller_wav = session_dir / "caller_audio.wav"

    if not agent_wav.exists() or not caller_wav.exists():
        raise FileNotFoundError(f"Missing WAV files in {session_dir}")

    log.info(f"Computing metrics for {session_dir}")

    # Load audio
    agent_pcm, agent_sr = _load_wav_pcm(agent_wav)
    caller_pcm, caller_sr = _load_wav_pcm(caller_wav)

    total_duration = max(
        len(agent_pcm) / (agent_sr * 2),
        len(caller_pcm) / (caller_sr * 2),
    )

    # Run VAD on both channels
    log.info("  Running VAD on agent audio...")
    agent_segments = compute_vad_timeline(agent_pcm, agent_sr)
    log.info(f"  Agent speech segments: {len(agent_segments)}")

    log.info("  Running VAD on caller audio...")
    caller_segments = compute_vad_timeline(caller_pcm, caller_sr)
    log.info(f"  Caller speech segments: {len(caller_segments)}")

    # Compute metrics
    latencies = compute_response_latencies(agent_segments, caller_segments)
    interruptions = compute_interruptions(agent_segments, caller_segments)
    silence_gaps = compute_silence_gaps(agent_segments, caller_segments, total_duration)

    # Count turns (alternating speech segments)
    all_turns = sorted(
        [("AGENT", s, e) for s, e in agent_segments]
        + [("COLDCALL", s, e) for s, e in caller_segments],
        key=lambda t: t[1],
    )
    turn_count = len(all_turns)

    metrics = {
        "call_duration_seconds": round(total_duration, 1),
        "turn_count": turn_count,
        "response_latency": {
            "values": latencies,
            "count": len(latencies),
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "mean": round(float(np.mean(latencies)), 3) if latencies else None,
        },
        "interruptions": {
            "count": len(interruptions),
            "events": interruptions,
        },
        "silence_gaps": {
            "count": len(silence_gaps),
            "threshold_seconds": SILENCE_GAP_THRESHOLD,
            "events": silence_gaps,
        },
        "vad_summary": {
            "agent_speech_segments": len(agent_segments),
            "agent_speech_seconds": round(
                sum(e - s for s, e in agent_segments), 1
            ),
            "caller_speech_segments": len(caller_segments),
            "caller_speech_seconds": round(
                sum(e - s for s, e in caller_segments), 1
            ),
        },
    }

    # Save
    metrics_path = session_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2))
    log.info(
        f"  Metrics saved: latency p50={metrics['response_latency']['p50']}, "
        f"interruptions={metrics['interruptions']['count']}, "
        f"silence_gaps={metrics['silence_gaps']['count']}, "
        f"turns={turn_count}"
    )

    return metrics
