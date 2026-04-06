"""Humanizer layer — transforms clean LLM text into natural speech patterns.

Sits between LLM output and TTS input in the Pipecat pipeline.
Applies: filler words, self-corrections, pause markers, sentence fragmentation.
"""

import logging
import random
import re

from pipecat.frames.frames import TextFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

log = logging.getLogger("coldcall")

# Filler words and their relative weights
FILLERS_START = [
    ("Um, ", 3),
    ("Uh, ", 3),
    ("So, ", 2),
    ("Well, ", 2),
    ("Let me think... ", 1),
    ("Hmm, ", 1),
    ("Oh, ", 1),
]

FILLERS_MID = [
    (", um,", 3),
    (", uh,", 3),
    (", like,", 1),
    ("... ", 2),
]

# Self-correction templates: (pattern, replacement_fn)
# These work on the buffered sentence text
CORRECTIONS = [
    # "I want X" → "I want— actually, I'd like X"
    (r"^(I want )(.*)", lambda m: f"I want— actually, I'd like {m.group(2)}"),
    # "I need to X" → "I need to— well, I should X"
    (r"^(I need to )(.*)", lambda m: f"I need to— well, I should {m.group(2)}"),
    # "It's X" → "It's— well, it's more like X"
    (r"^(It's )(.*)", lambda m: f"It's— well, it's more like {m.group(2)}"),
    # "Can you X" → "Can you— I mean, would you X"
    (r"^(Can you )(.*)", lambda m: f"Can you— I mean, would you {m.group(2)}"),
]

# Clause-break conjunctions for fragmentation
FRAGMENT_POINTS = ["and ", "but ", "because ", "since ", "although ", "however "]

# Pause markers that TTS interprets as natural breaks
CLAUSE_BREAK = "... "
THINKING_PAUSE = "... "


class HumanizerProcessor(FrameProcessor):
    """Transforms LLM text output into more natural-sounding speech.

    Buffers incoming TextFrames into complete sentences, applies humanization
    transforms, then emits the modified text for TTS.
    """

    def __init__(
        self,
        filler_rate: float = 0.18,
        correction_rate: float = 0.05,
        fragment_rate: float = 0.20,
        pause_rate: float = 0.25,
        enabled: bool = True,
    ):
        super().__init__()
        self._filler_rate = filler_rate
        self._correction_rate = correction_rate
        self._fragment_rate = fragment_rate
        self._pause_rate = pause_rate
        self._enabled = enabled
        self._buffer = ""
        self._turn_count = 0

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if not self._enabled or not isinstance(frame, TextFrame) or isinstance(frame, TranscriptionFrame):
            await self.push_frame(frame, direction)
            return

        self._buffer += frame.text

        # Check for sentence boundaries
        while True:
            match = re.search(r'[.!?](?:\s|$)', self._buffer)
            if not match:
                break

            end = match.end()
            sentence = self._buffer[:end].strip()
            self._buffer = self._buffer[end:]

            if sentence:
                transformed = self._humanize(sentence)
                # Emit as a single TextFrame
                await self.push_frame(TextFrame(text=transformed), direction)
                self._turn_count += 1

        # If buffer has content but no sentence boundary yet, hold it
        # (it will be flushed when next sentence-ending token arrives)

    def _humanize(self, text: str) -> str:
        """Apply humanization transforms to a complete sentence."""
        # Skip very short utterances (greetings, "yes", "no", etc.)
        if len(text.split()) <= 3:
            return text

        # 1. Self-correction (rare, ~5%)
        if random.random() < self._correction_rate:
            text = self._apply_correction(text)
            return text  # Don't stack other transforms on corrections

        # 2. Fragment long sentences at conjunction points (~20%)
        if len(text.split()) > 8 and random.random() < self._fragment_rate:
            text = self._fragment(text)

        # 3. Insert filler word (~18%)
        if random.random() < self._filler_rate:
            text = self._add_filler(text)

        # 4. Add thinking pause before responding (~25%, first sentence only)
        if self._turn_count == 0 and random.random() < self._pause_rate:
            text = THINKING_PAUSE + text

        return text

    def _add_filler(self, text: str) -> str:
        """Insert a filler word at the start or middle of the sentence."""
        if random.random() < 0.75:
            # Start of sentence
            filler = _weighted_choice(FILLERS_START)
            return filler + text[0].lower() + text[1:]
        else:
            # Mid-sentence: insert after first clause boundary (comma)
            comma_pos = text.find(", ")
            if comma_pos > 0 and comma_pos < len(text) - 5:
                filler = _weighted_choice(FILLERS_MID)
                return text[:comma_pos] + filler + text[comma_pos + 2:]
            # Fallback to start
            filler = _weighted_choice(FILLERS_START)
            return filler + text[0].lower() + text[1:]

    def _apply_correction(self, text: str) -> str:
        """Apply a self-correction pattern."""
        for pattern, replacement in CORRECTIONS:
            m = re.match(pattern, text, re.IGNORECASE)
            if m:
                return replacement(m)
        return text

    def _fragment(self, text: str) -> str:
        """Split a long sentence at a natural conjunction point."""
        for conj in FRAGMENT_POINTS:
            idx = text.lower().find(conj)
            if 5 < idx < len(text) - 10:
                return text[:idx] + CLAUSE_BREAK + text[idx:]
        return text


def _weighted_choice(options: list[tuple[str, int]]) -> str:
    """Pick from a weighted list of (value, weight) tuples."""
    items, weights = zip(*options)
    return random.choices(items, weights=weights, k=1)[0]
