"""Tests for audio metrics computation logic."""

from coldcall.metrics import (
    compute_response_latencies,
    compute_interruptions,
    compute_silence_gaps,
    percentile,
)


class TestResponseLatencies:
    def test_basic_latencies(self):
        agent = [(5.3, 8.0), (11.8, 14.0)]
        caller = [(2.5, 5.0), (8.5, 11.0)]
        lat = compute_response_latencies(agent, caller)
        assert len(lat) == 2
        assert lat[0] == 0.3  # 5.3 - 5.0
        assert lat[1] == 0.8  # 11.8 - 11.0

    def test_no_preceding_caller(self):
        agent = [(0.5, 2.0)]  # agent speaks first, no caller before
        caller = [(3.0, 5.0)]
        lat = compute_response_latencies(agent, caller)
        assert lat == []

    def test_empty_segments(self):
        assert compute_response_latencies([], []) == []
        assert compute_response_latencies([(1, 2)], []) == []
        assert compute_response_latencies([], [(1, 2)]) == []


class TestInterruptions:
    def test_no_interruptions(self):
        agent = [(5.0, 8.0)]
        caller = [(2.0, 4.5)]
        assert len(compute_interruptions(agent, caller)) == 0

    def test_agent_interrupts_caller(self):
        agent = [(3.0, 5.0)]
        caller = [(2.0, 4.0)]  # caller still speaking when agent starts at 3.0
        ints = compute_interruptions(agent, caller)
        assert len(ints) == 1
        assert ints[0]["time"] == 3.0
        assert ints[0]["overlap_seconds"] == 1.0

    def test_empty(self):
        assert compute_interruptions([], []) == []


class TestSilenceGaps:
    def test_gap_detected(self):
        agent = [(0, 2)]
        caller = [(5, 7)]
        gaps = compute_silence_gaps(agent, caller, 10.0)
        assert len(gaps) == 2  # gap 2-5 (3s) and gap 7-10 (3s)
        assert gaps[0]["duration"] == 3.0
        assert gaps[1]["duration"] == 3.0

    def test_no_gap_under_threshold(self):
        agent = [(0, 2)]
        caller = [(3, 5)]  # 1s gap, under 2s threshold
        gaps = compute_silence_gaps(agent, caller, 5.0)
        assert len(gaps) == 0

    def test_empty_segments(self):
        gaps = compute_silence_gaps([], [], 10.0)
        assert len(gaps) == 1  # whole call is silence
        assert gaps[0]["duration"] == 10.0


class TestPercentile:
    def test_basic(self):
        assert percentile([1, 2, 3, 4, 5], 50) == 3.0

    def test_empty(self):
        assert percentile([], 50) is None

    def test_single(self):
        assert percentile([0.5], 50) == 0.5
        assert percentile([0.5], 99) == 0.5
