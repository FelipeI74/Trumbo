from __future__ import annotations

import hashlib
import json
import re
from typing import Any
import logging

from fastapi import HTTPException

from app.database import connect, rows
from app.domain import parse_character_cue, resolve_character_alias
from .character_service import deserialize_semantic_lines, get_project_character_names, get_project_character_names as _get_project_character_names

logger = logging.getLogger(__name__)


# Matches INT./EXT./INT/EXT. etc.; period makes trailing space optional
_HEADING_PREFIX_RE = re.compile(
    r"^(INT\.?/EXT\.?|EXT\.?/INT\.?|I/E\.?|E/I\.?|INT\.?|EXT\.?)(?:(?<=\.)\s*|\s+)",
    re.IGNORECASE,
)

_HEADING_SPLIT_RE = re.compile(
    r"\s+[-–—]\s+"
)

_KNOWN_TIME_OF_DAY = frozenset({
    "DIA",
    "DÍA",
    "NOCHE",
    "AMANECER",
    "ATARDECER",
    "TARDE",
})

_TIME_OF_DAY_SUFFIX_RE = re.compile(
    r"^(D[IÍ]A|NOCHE|AMANECER|ATARDECER|TARDE)(?:[\.,;:!?]+)?(?:\([^)]*\))?$"
)


def _parse_heading_fields(heading: str) -> dict:
    """Conservative best-effort split of a scene heading into its components."""
    text = heading.strip().upper()
    match = _HEADING_PREFIX_RE.match(text)
    if not match:
        return {
            "int_ext": "",
            "location": "",
            "sublocation": "",
            "time_of_day": "",
        }

    int_ext = match.group(1).upper()
    remainder = text[match.end():].strip()
    parts = [
        p.strip()
        for p in _HEADING_SPLIT_RE.split(remainder)
        if p.strip()
    ]

    if not parts:
        return {
            "int_ext": int_ext,
            "location": "",
            "sublocation": "",
            "time_of_day": "",
        }

    if len(parts) == 1:
        return {
            "int_ext": int_ext,
            "location": parts[0],
            "sublocation": "",
            "time_of_day": "",
        }

    time_of_day_match = _TIME_OF_DAY_SUFFIX_RE.match(
        parts[-1]
    )

    if time_of_day_match:
        return {
            "int_ext": int_ext,
            "location": parts[0],
            "sublocation": " - ".join(parts[1:-1]),
            "time_of_day": time_of_day_match.group(1),
        }

    return {
        "int_ext": int_ext,
        "location": parts[0],
        "sublocation": " - ".join(parts[1:]),
        "time_of_day": "",
    }

parse_heading_fields = _parse_heading_fields


def build_project_scheduling_input(
    project_id: int,
) -> dict:
    with connect() as connection:
        project_exists = connection.execute(
            """
            SELECT 1
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project_exists is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        scene_rows = connection.execute(
            """
            SELECT
                id,
                scene_number,
                production_number,
                heading,
                body,
                runtime_seconds,
                semantic_lines
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number, id
            """,
            (project_id,),
        ).fetchall()

        resource_rows = connection.execute(
            """
            SELECT
                breakdown_items.scene_id,
                breakdown_items.category,
                breakdown_items.name
            FROM breakdown_items
            JOIN scenes
                ON scenes.id = breakdown_items.scene_id
            WHERE scenes.project_id = ?
              AND breakdown_items.state != 'rejected'
            ORDER BY scenes.scene_number, breakdown_items.name
            """,
            (project_id,),
        ).fetchall()

        alias_rows = connection.execute(
            """
            SELECT alias_name, primary_name
            FROM character_aliases
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchall()

        import unicodedata
        
        def normalize_name(name: str) -> str:
            """Elimina tildes y convierte a minúsculas para comparar."""
            if not name:
                return ""
            # Normalizar a NFD (descomponer caracteres acentuados) y eliminar los diacríticos
            normalized = unicodedata.normalize("NFD", name)
            return "".join(c for c in normalized if unicodedata.category(c) != "Mn").casefold()

        aliases_map = {
            normalize_name(row["alias_name"]): row["primary_name"]
            for row in alias_rows
        }
        known_characters = _get_project_character_names(
            connection,
            project_id,
        )

    resources_by_scene: dict[int, list[str]] = {}
    seen_resources_by_scene: dict[int, set[str]] = {}
    scene_cast_by_scene: dict[int, list[str]] = {}
    seen_scene_cast_by_scene: dict[int, set[str]] = {}

    for resource_row in resource_rows:
        scene_id = int(resource_row["scene_id"])
        resource_category = str(resource_row["category"] or "").strip()
        resource_name = str(resource_row["name"] or "").strip()

        if not resource_name:
            continue

        resource_key = resource_name.casefold()
        if resource_category.casefold() in {"cast", "scene_cast", "character"}:
            seen_scene_cast = seen_scene_cast_by_scene.setdefault(
                scene_id,
                set(),
            )

            if resource_key in seen_scene_cast:
                continue

            seen_scene_cast.add(resource_key)
            scene_cast_by_scene.setdefault(
                scene_id,
                [],
            ).append(resource_name)
            continue

        seen_resources = seen_resources_by_scene.setdefault(
            scene_id,
            set(),
        )

        if resource_key in seen_resources:
            continue

        seen_resources.add(resource_key)
        resources_by_scene.setdefault(
            scene_id,
            [],
        ).append(resource_name)

    scenes: list[dict] = []

    for script_order, scene_row in enumerate(
        scene_rows,
        start=1,
    ):
        scene_id = int(scene_row["id"])
        heading_fields = _parse_heading_fields(
            str(scene_row["heading"] or "")
        )
        seen_characters: set[str] = set()
        characters: list[str] = []
        voice_over_characters: list[str] = []

        for line in deserialize_semantic_lines(
            scene_row["semantic_lines"]
        ):
            if line.get("type") != "character":
                continue

            for personaje in parse_character_cue(line.get("text") or ""):
                name = resolve_character_alias(personaje["name"], aliases_map)
                key = name.casefold()

                if not name or key in seen_characters:
                    continue

                seen_characters.add(key)
                characters.append(name)

                if personaje["is_voice_over"]:
                    voice_over_characters.append(name)

        body_text = str(scene_row["body"] or "").upper()
        for known_character in known_characters:
            character_key = known_character.casefold()
            if character_key in seen_characters:
                continue

            pattern = rf"(?<!\w){re.escape(known_character)}(?!\w)"
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match is None:
                continue

            prefix = body_text[:match.start()]
            if re.search(r"\b(?:DE|DEL)\s+$", prefix, re.IGNORECASE):
                continue

            seen_characters.add(character_key)
            characters.append(known_character)

        scene_cast = list(characters)
        seen_scene_cast = {name.strip().casefold() for name in scene_cast}
        for name in scene_cast_by_scene.get(scene_id, []):
            resolved = resolve_character_alias(name, aliases_map)
            key = resolved.strip().casefold()
            if not key or key in seen_scene_cast:
                continue
            seen_scene_cast.add(key)
            scene_cast.append(resolved)

        scenes.append(
            {
                "scene_id": scene_id,
                "scene_number": int(scene_row["scene_number"]),
                "production_number": scene_row["production_number"],
                "script_order": script_order,
                "int_ext": heading_fields["int_ext"],
                "location": heading_fields["location"],
                "sublocation": heading_fields["sublocation"],
                "time_of_day": heading_fields["time_of_day"],
                "runtime_seconds": int(scene_row["runtime_seconds"] or 0),
                "characters": characters,
                "voice_over_characters": voice_over_characters,
                "scene_cast": scene_cast,
                "resources": resources_by_scene.get(scene_id, []),
            }
        )

    return {"scenes": scenes}

_build_project_scheduling_input = build_project_scheduling_input


def _schedule_input_fingerprint(
    scenes: list[dict],
    shoot_rate_seconds: int,
) -> str:
    serialized = json.dumps(
        {
            "scenes": scenes,
            "shoot_rate_seconds": shoot_rate_seconds,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()

schedule_input_fingerprint = _schedule_input_fingerprint


def _validate_manual_schedule_days(
    manual_days: Any,
    calculated_days: Any,  # No se usa, por compatibilidad
    scenes: list[dict],
) -> list[dict[str, Any]] | None:
    if not isinstance(manual_days, list):
        return None

    scene_by_id = {
        int(scene["scene_id"]): scene
        for scene in scenes
        if scene.get("scene_id") is not None
    }
    all_scene_ids = set(scene_by_id.keys())
    time_by_scene_id = {
        int(scene["scene_id"]): str(scene.get("time_of_day") or "")
        for scene in scenes
    }

    validated_days: list[dict[str, Any]] = []
    all_seen: set[int] = set()
    orphan_ids: set[int] = set()

    for manual_day in manual_days:
        if not isinstance(manual_day, dict):
            return None

        scene_ids = manual_day.get("scene_ids")
        if not isinstance(scene_ids, list):
            return None

        if any(
            isinstance(scene_id, bool) or not isinstance(scene_id, int)
            for scene_id in scene_ids
        ):
            return None

        clean_ids = []
        for scene_id in scene_ids:
            if scene_id in all_seen:
                continue
            if scene_id not in all_scene_ids:
                orphan_ids.add(scene_id)
                continue
            all_seen.add(scene_id)
            clean_ids.append(scene_id)

        if not clean_ids:
            continue

        # Corregir el orden DÍA/NOCHE dentro de la jornada
        day_of = [s for s in clean_ids if time_by_scene_id.get(s, "").strip().casefold() != "noche"]
        night_of = [s for s in clean_ids if time_by_scene_id.get(s, "").strip().casefold() == "noche"]
        ordered_ids = day_of + night_of

        validated_days.append({
            "day": len(validated_days) + 1,
            "scene_ids": ordered_ids,
        })

    missing = all_scene_ids - all_seen
    if missing:
        validated_days.append({
            "day": len(validated_days) + 1,
            "scene_ids": sorted(missing),
        })

    if orphan_ids:
        logger.warning(
            "Manual schedule has orphan scene ids (ignored): %s",
            sorted(orphan_ids),
        )

    return validated_days