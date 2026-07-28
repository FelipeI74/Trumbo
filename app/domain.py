from __future__ import annotations

import re
from dataclasses import dataclass

WORDS_PER_MINUTE = 135
DIALOGUE_WEIGHT = 1.20
ACTION_WEIGHT = 0.90
MINIMUM_SCENE_SECONDS = 3


@dataclass(frozen=True)
class RuntimeEstimate:
    seconds: int
    formatted: str


def estimate_runtime(text: str) -> RuntimeEstimate:
    clean = text.strip()
    if not clean:
        return RuntimeEstimate(seconds=0, formatted="00:00")

    blocks = [block.strip() for block in re.split(r"\n\s*\n", clean) if block.strip()]
    weighted_words = 0.0

    for block in blocks:
        words = re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ'-]+\b", block)
        if not words:
            continue

        first_line = block.splitlines()[0].strip()
        is_character_cue = (
            first_line.isupper()
            and len(first_line) <= 35
            and not first_line.startswith(("INT.", "EXT.", "INT/EXT.", "EXT/INT."))
        )
        weight = DIALOGUE_WEIGHT if is_character_cue else ACTION_WEIGHT
        weighted_words += len(words) * weight

    seconds = round((weighted_words / WORDS_PER_MINUTE) * 60)
    seconds = max(MINIMUM_SCENE_SECONDS, seconds)
    return RuntimeEstimate(seconds=seconds, formatted=format_seconds(seconds))


def format_seconds(seconds: int) -> str:
    minutes, remaining = divmod(max(0, seconds), 60)
    return f"{minutes:02d}:{remaining:02d}"
