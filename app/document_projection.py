from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any


LINE_TYPES = {
    "heading",
    "action",
    "character",
    "parenthetical",
    "dialogue",
    "transition",
}

HEADING_PREFIX_REGEX = re.compile(r"^(INT\.|EXT\.)\s*", re.IGNORECASE)
HEADING_TOKEN_ONLY_REGEX = re.compile(r"^(INT\.|EXT\.)$", re.IGNORECASE)
HEADING_COMPLETE_REGEX = re.compile(r"^(INT\.|EXT\.)\s*.+", re.IGNORECASE)

TRANSITION_IN_REGEX = re.compile(r"^FADE IN:$", re.IGNORECASE)
TRANSITION_OUT_REGEX = re.compile(
    r"^(CUT TO:|FADE OUT:|MATCH CUT:|SMASH CUT:|JUMP CUT:|DISSOLVE TO:|WIPE TO:|CORTE A:|FUNDIDO A:|DISOLVENCIA A:)$",
    re.IGNORECASE,
)

DOCUMENT_NAMESPACE = uuid.UUID("2a638838-8fc5-4c96-9d74-9e6f6f1ce6f2")
LINE_NAMESPACE = uuid.UUID("c849548f-7b6a-4ca8-9851-012b2b132d31")


@dataclass(frozen=True)
class ParityResult:
    ok: bool
    errors: list[str]


def _is_heading_prefix_text(value: str) -> bool:
    return bool(HEADING_PREFIX_REGEX.match((value or "").strip()))


def _is_heading_token_only(value: str) -> bool:
    return bool(HEADING_TOKEN_ONLY_REGEX.match((value or "").strip()))


def is_complete_scene_heading_text(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    return bool(HEADING_COMPLETE_REGEX.match(text)) and not _is_heading_token_only(text)


def _is_transition_text(value: str) -> bool:
    text = (value or "").strip()
    return bool(TRANSITION_IN_REGEX.match(text) or TRANSITION_OUT_REGEX.match(text))


def _infer_line_type(text: str, previous_type: str | None = None) -> str:
    value = (text or "").strip()

    if not value:
        if previous_type in {"character", "parenthetical"}:
            return "dialogue"
        return "action"

    if _is_heading_prefix_text(value):
        return "heading"

    if value.startswith("(") and value.endswith(")"):
        return "parenthetical"

    if _is_transition_text(value):
        return "transition"

    looks_uppercase = value == value.upper() and bool(re.search(r"[A-ZÁÉÍÓÚÜÑ]", value))
    if looks_uppercase and len(value) <= 45 and not re.search(r"[.!?]$", value):
        return "character"

    if previous_type in {"character", "parenthetical", "dialogue"}:
        return "dialogue"

    return "action"


def _normalize_semantic_lines(lines: Any) -> list[dict[str, str]]:
    if not isinstance(lines, list):
        return []

    result: list[dict[str, str]] = []
    for item in lines:
        if not isinstance(item, dict):
            continue
        line_type = item.get("type")
        text = item.get("text")
        if line_type in LINE_TYPES and isinstance(text, str):
            result.append({"type": line_type, "text": text})
    return result


def _scene_to_semantic_lines(scene: dict[str, Any]) -> list[dict[str, str]]:
    server_lines = _normalize_semantic_lines(scene.get("semantic_lines"))
    if server_lines:
        return server_lines

    result: list[dict[str, str]] = []
    heading = str(scene.get("heading") or "").strip()
    if heading:
        result.append({"type": "heading", "text": heading})

    body = str(scene.get("body") or "")
    body_lines = re.split(r"\r?\n", body)

    previous_type = "heading" if heading else "action"
    for text in body_lines:
        line_type = _infer_line_type(text, previous_type)
        result.append({"type": line_type, "text": text})
        previous_type = line_type

    if not result:
        result.append({"type": "action", "text": ""})

    if len(result) == 1 and result[0]["type"] == "heading":
        result.append({"type": "action", "text": ""})

    return result


def project_document_id(project_id: int) -> str:
    return str(uuid.uuid5(DOCUMENT_NAMESPACE, f"adumn:project:{project_id}"))


def backfill_line_uuid(project_id: int, scene_id: int, line_index: int) -> str:
    seed = f"adumn:{project_id}:{scene_id}:{line_index}"
    return str(uuid.uuid5(LINE_NAMESPACE, seed))


def project_document_from_scenes(
    project_id: int,
    scenes: list[dict[str, Any]],
    existing_lines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ordered_scenes = sorted(
        scenes,
        key=lambda item: (int(item.get("scene_number") or 0), int(item.get("id") or 0)),
    )

    persisted_by_origin: dict[tuple[int, int], str] = {}
    for persisted in existing_lines or []:
        origin_scene_id = persisted.get("source_scene_id")
        origin_line_index = persisted.get("source_line_index")
        line_uuid = persisted.get("uuid")
        if isinstance(origin_scene_id, int) and isinstance(origin_line_index, int) and isinstance(line_uuid, str):
            persisted_by_origin[(origin_scene_id, origin_line_index)] = line_uuid

    lines: list[dict[str, Any]] = []
    position = 0

    for scene in ordered_scenes:
        scene_id = int(scene.get("id") or 0)
        semantic_lines = _scene_to_semantic_lines(scene)

        for line_index, semantic_line in enumerate(semantic_lines):
            persisted_uuid = persisted_by_origin.get((scene_id, line_index))
            line_uuid = persisted_uuid or backfill_line_uuid(project_id, scene_id, line_index)

            lines.append(
                {
                    "uuid": line_uuid,
                    "document_id": project_document_id(project_id),
                    "position": position,
                    "type": semantic_line["type"],
                    "text": semantic_line["text"],
                    "source_scene_id": scene_id,
                    "source_line_index": line_index,
                }
            )
            position += 1

    return {
        "document": {
            "id": project_document_id(project_id),
            "project_id": project_id,
        },
        "lines": lines,
    }


def derive_scenes_from_document_lines(lines: list[dict[str, Any]]) -> dict[str, Any]:
    ordered_lines = sorted(lines, key=lambda item: int(item.get("position") or 0))

    preface_lines: list[dict[str, str]] = []
    chunks: list[list[dict[str, str]]] = []
    current_chunk: list[dict[str, str]] | None = None

    for line in ordered_lines:
        line_type = str(line.get("type") or "action")
        text = str(line.get("text") or "")
        normalized = {"type": line_type, "text": text}

        if is_complete_scene_heading_text(text):
            if current_chunk is not None:
                chunks.append(current_chunk)
            current_chunk = [normalized]
            continue

        if current_chunk is None:
            preface_lines.append(normalized)
            continue

        current_chunk.append(normalized)

    if current_chunk is not None:
        chunks.append(current_chunk)

    scenes: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        heading = chunk[0]["text"].strip()
        body = "\n".join(item["text"] for item in chunk[1:])
        scenes.append(
            {
                "scene_number": index,
                "heading": heading,
                "body": body,
                "semantic_lines": chunk,
            }
        )

    return {
        "preface_lines": preface_lines,
        "scenes": scenes,
    }


def _scene_view_for_parity(scene: dict[str, Any]) -> dict[str, Any]:
    semantic_lines = _scene_to_semantic_lines(scene)
    heading_line = next((item for item in semantic_lines if item["type"] == "heading"), None)
    heading = (heading_line["text"] if heading_line else "").strip()
    if heading_line is None:
        body_lines = [item["text"] for item in semantic_lines]
    else:
        heading_consumed = False
        body_lines: list[str] = []
        for item in semantic_lines:
            if not heading_consumed and item is heading_line:
                heading_consumed = True
                continue
            body_lines.append(item["text"])

    return {
        "heading": heading,
        "body": "\n".join(body_lines),
        "semantic_lines": semantic_lines,
    }


def audit_scene_parity(
    original_scenes: list[dict[str, Any]],
    rebuilt_scenes: list[dict[str, Any]],
) -> ParityResult:
    errors: list[str] = []

    expected = [_scene_view_for_parity(scene) for scene in original_scenes]

    if len(expected) != len(rebuilt_scenes):
        errors.append(
            f"Cantidad de escenas distinta: esperado={len(expected)} reconstruido={len(rebuilt_scenes)}"
        )

    for idx, (left, right) in enumerate(zip(expected, rebuilt_scenes), start=1):
        if left["heading"] != right.get("heading", ""):
            errors.append(
                f"Escena {idx}: heading distinto esperado={left['heading']!r} reconstruido={right.get('heading', '')!r}"
            )

        if left["body"] != right.get("body", ""):
            errors.append(
                f"Escena {idx}: body distinto esperado={left['body']!r} reconstruido={right.get('body', '')!r}"
            )

        right_semantic = _normalize_semantic_lines(right.get("semantic_lines"))
        if left["semantic_lines"] != right_semantic:
            errors.append(f"Escena {idx}: semantic_lines distintas")

    return ParityResult(ok=not errors, errors=errors)


def assert_scene_parity(
    original_scenes: list[dict[str, Any]],
    rebuilt_scenes: list[dict[str, Any]],
) -> None:
    result = audit_scene_parity(original_scenes, rebuilt_scenes)
    if result.ok:
        return
    raise AssertionError(" | ".join(result.errors))