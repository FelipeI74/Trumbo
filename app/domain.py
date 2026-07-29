from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from enum import StrEnum

WORDS_PER_MINUTE = 135
DIALOGUE_WEIGHT = 1.20
ACTION_WEIGHT = 0.90
MINIMUM_SCENE_SECONDS = 3

SCENE_HEADING_PREFIXES = (
    "INT.", "EXT.", "INT/EXT.", "EXT/INT.", "I/E.", "E/I.",
    "INT ", "EXT ", "INT/EXT ", "EXT/INT ",
)
TRANSITIONS = {
    "CORTE A:", "CORTE:", "FUNDIDO A:", "FUNDIDO:", "DISOLVENCIA A:",
    "MATCH CUT:", "JUMP CUT:", "IRIS OUT:", "IRIS IN:", "FADE OUT:",
    "FADE IN:", "CUT TO:", "SMASH CUT TO:", "DISSOLVE TO:",
}


class ScriptElementType(StrEnum):
    HEADING = "heading"
    ACTION = "action"
    CHARACTER = "character"
    DIALOGUE = "dialogue"
    PARENTHETICAL = "parenthetical"
    TRANSITION = "transition"
    EMPTY = "empty"


@dataclass(frozen=True)
class RuntimeEstimate:
    seconds: int
    formatted: str


@dataclass(frozen=True)
class ScriptElement:
    line_number: int
    type: ScriptElementType
    text: str
    confidence: float

    def to_dict(self) -> dict:
        value = asdict(self)
        value["type"] = self.type.value
        return value


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def is_scene_heading(line: str) -> bool:
    normalized = _normalize_line(line).upper()
    if not normalized:
        return False
    return normalized.startswith(SCENE_HEADING_PREFIXES)


def is_transition(line: str) -> bool:
    normalized = _normalize_line(line).upper()
    if not normalized:
        return False
    return normalized in TRANSITIONS or (
        normalized.endswith(" A:")
        and len(normalized) <= 35
        and normalized == normalized.upper()
    )


def is_parenthetical(line: str) -> bool:
    normalized = line.strip()
    return len(normalized) >= 2 and normalized.startswith("(") and normalized.endswith(")")


def is_character_cue(line: str) -> bool:
    normalized = _normalize_line(line)
    if not normalized or is_scene_heading(normalized) or is_transition(normalized):
        return False
    if len(normalized) > 40 or normalized.endswith((".", "?", "!", ":")):
        return False
    if normalized != normalized.upper():
        return False
    # Admite extensiones frecuentes: PEDRO (V.O.), MARTA (O.S.), JUAN (CONT'D)
    return bool(re.fullmatch(r"[A-ZÁÉÍÓÚÜÑ0-9 ._'\-()]+", normalized))


def parse_screenplay(heading: str, body: str) -> list[ScriptElement]:
    """Clasifica el guion sin modificarlo.

    Es una primera versión determinista y explicable. La clasificación se basa en
    convenciones de formato, no en decisiones creativas ni en generación de texto.
    """
    elements: list[ScriptElement] = []
    line_number = 1

    if heading.strip():
        heading_type = ScriptElementType.HEADING if is_scene_heading(heading) else ScriptElementType.ACTION
        elements.append(ScriptElement(line_number, heading_type, heading.strip(), 1.0 if heading_type == ScriptElementType.HEADING else 0.55))
        line_number += 1

    lines = body.splitlines()
    previous_non_empty: ScriptElementType | None = elements[-1].type if elements else None

    for raw_line in lines:
        text = raw_line.strip()
        if not text:
            elements.append(ScriptElement(line_number, ScriptElementType.EMPTY, "", 1.0))
            line_number += 1
            continue

        if is_scene_heading(text):
            element_type = ScriptElementType.HEADING
            confidence = 1.0
        elif is_transition(text):
            element_type = ScriptElementType.TRANSITION
            confidence = 0.98
        elif is_parenthetical(text) and previous_non_empty in {ScriptElementType.CHARACTER, ScriptElementType.DIALOGUE}:
            element_type = ScriptElementType.PARENTHETICAL
            confidence = 0.95
        elif is_character_cue(text):
            element_type = ScriptElementType.CHARACTER
            confidence = 0.92
        elif previous_non_empty in {ScriptElementType.CHARACTER, ScriptElementType.PARENTHETICAL, ScriptElementType.DIALOGUE}:
            element_type = ScriptElementType.DIALOGUE
            confidence = 0.88
        else:
            element_type = ScriptElementType.ACTION
            confidence = 0.85

        elements.append(ScriptElement(line_number, element_type, text, confidence))
        previous_non_empty = element_type
        line_number += 1

    return elements


def screenplay_summary(heading: str, body: str) -> dict:
    elements = parse_screenplay(heading, body)
    counts = {element_type.value: 0 for element_type in ScriptElementType if element_type != ScriptElementType.EMPTY}
    characters: list[str] = []

    for element in elements:
        if element.type != ScriptElementType.EMPTY:
            counts[element.type.value] += 1
        if element.type == ScriptElementType.CHARACTER:
            base_name = re.sub(r"\s*\([^)]*\)\s*$", "", element.text).strip()
            if base_name and base_name not in characters:
                characters.append(base_name)

    return {
        "counts": counts,
        "characters": characters,
        "elements": [element.to_dict() for element in elements],
    }


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
        weight = DIALOGUE_WEIGHT if is_character_cue(first_line) else ACTION_WEIGHT
        weighted_words += len(words) * weight

    seconds = round((weighted_words / WORDS_PER_MINUTE) * 60)
    seconds = max(MINIMUM_SCENE_SECONDS, seconds)
    return RuntimeEstimate(seconds=seconds, formatted=format_seconds(seconds))


def format_seconds(seconds: int) -> str:
    minutes, remaining = divmod(max(0, seconds), 60)
    return f"{minutes:02d}:{remaining:02d}"
