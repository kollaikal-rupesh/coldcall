"""Tests for report generation."""

import json
import math
import struct
import wave
from pathlib import Path

import pytest

from coldcall.report import generate_reports, _escape


class TestEscape:
    def test_html_entities(self):
        assert _escape("<script>alert('xss')</script>") == "&lt;script&gt;alert('xss')&lt;/script&gt;"
        assert _escape('He said "hello"') == "He said &quot;hello&quot;"
        assert _escape("A & B") == "A &amp; B"

    def test_plain_text(self):
        assert _escape("Hello world") == "Hello world"
        assert _escape("") == ""


class TestReportGeneration:
    def _create_mock_session(self, tmp_path: Path) -> Path:
        d = tmp_path / "session"
        d.mkdir()

        (d / "metadata.json").write_text(json.dumps({
            "call_sid": "CA_test", "scenario": "test",
            "start_time": "2026-01-01T00:00:00+00:00",
            "end_time": "2026-01-01T00:00:30+00:00",
            "duration_seconds": 30.0, "transcript_turns": 2,
        }))

        (d / "transcript.json").write_text(json.dumps({"turns": [
            {"speaker": "AGENT", "text": "Hello", "start_time": 0.5, "end_time": 1.0},
            {"speaker": "COLDCALL", "text": "Hi there", "start_time": 1.5, "end_time": 2.0},
        ]}))

        (d / "evaluation.json").write_text(json.dumps({
            "overall": "PASS", "summary": "Good",
            "criteria": [{"id": "test", "result": "PASS", "explanation": "ok"}],
        }))

        (d / "metrics.json").write_text(json.dumps({
            "call_duration_seconds": 30.0, "turn_count": 2,
            "response_latency": {"values": [0.5], "count": 1, "p50": 0.5, "p95": 0.5, "p99": 0.5, "mean": 0.5},
            "interruptions": {"count": 0, "events": []},
            "silence_gaps": {"count": 0, "events": []},
        }))

        # Tiny WAV
        samples = struct.pack("<h", 0) * 800
        with wave.open(str(d / "mixed_audio.wav"), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(samples)

        return d

    def test_generates_both_files(self, tmp_path):
        d = self._create_mock_session(tmp_path)
        json_path, html_path = generate_reports(d)
        assert json_path.exists()
        assert html_path.exists()

    def test_json_report_structure(self, tmp_path):
        d = self._create_mock_session(tmp_path)
        json_path, _ = generate_reports(d)
        report = json.loads(json_path.read_text())
        assert report["result"] == "pass"
        assert report["scenario"] == "test"
        assert report["metrics"]["latency_p50_ms"] == 500
        assert len(report["criteria"]) == 1

    def test_html_report_has_audio(self, tmp_path):
        d = self._create_mock_session(tmp_path)
        _, html_path = generate_reports(d)
        html = html_path.read_text()
        assert "data:audio/wav;base64" in html
        assert "<audio" in html

    def test_html_escapes_xss(self, tmp_path):
        d = self._create_mock_session(tmp_path)
        # Inject XSS into transcript
        (d / "transcript.json").write_text(json.dumps({"turns": [
            {"speaker": "AGENT", "text": "<script>alert(1)</script>", "start_time": 0, "end_time": 1},
        ]}))
        _, html_path = generate_reports(d)
        html = html_path.read_text()
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html
