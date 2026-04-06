"""Tests for humanizer text transforms."""

import random

from coldcall.humanizer import HumanizerProcessor


class TestHumanizer:
    def test_short_text_unchanged(self):
        h = HumanizerProcessor(filler_rate=1.0)
        assert h._humanize("Yes.") == "Yes."
        assert h._humanize("OK.") == "OK."
        assert h._humanize("No.") == "No."

    def test_filler_insertion(self):
        random.seed(1)
        h = HumanizerProcessor(filler_rate=1.0, correction_rate=0.0, fragment_rate=0.0)
        result = h._humanize("I need to cancel my appointment for Thursday.")
        assert result != "I need to cancel my appointment for Thursday."
        # Should start with a filler
        assert any(result.startswith(f) for f in ["Um,", "Uh,", "So,", "Well,", "Let me think", "Hmm,", "Oh,"])

    def test_correction_applied(self):
        h = HumanizerProcessor(filler_rate=0.0, correction_rate=1.0)
        result = h._humanize("I want a refund please.")
        assert "actually" in result or "well" in result

    def test_fragmentation(self):
        h = HumanizerProcessor(filler_rate=0.0, correction_rate=0.0, fragment_rate=1.0)
        result = h._humanize("I ordered shoes last Tuesday and they arrived damaged.")
        assert "..." in result

    def test_disabled(self):
        h = HumanizerProcessor(enabled=False)
        text = "I need to cancel my appointment."
        assert h._humanize(text) == text

    def test_empty_text(self):
        h = HumanizerProcessor(filler_rate=1.0)
        # Empty and whitespace should not crash
        assert h._humanize("") == ""
        assert h._humanize("   ") == "   "

    def test_no_fragmentation_on_short_sentences(self):
        h = HumanizerProcessor(filler_rate=0.0, correction_rate=0.0, fragment_rate=1.0)
        result = h._humanize("Hello there.")
        assert "..." not in result  # too short to fragment
