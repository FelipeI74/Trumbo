from __future__ import annotations

from typing import Any


def _flatten_scene_ids(days: list[dict[str, Any]]) -> list[int]:
    scene_ids: list[int] = []
    for day in days:
        for scene_id in day.get("scene_ids", []):
            scene_ids.append(int(scene_id))
    return scene_ids


def _scene_lookup(scenes: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {
        int(scene["scene_id"]): scene
        for scene in scenes
    }


def _count_inversions(keys: list[tuple[int, int]]) -> int:
    inversions = 0
    for index in range(len(keys)):
        left = keys[index]
        for right in keys[index + 1 :]:
            if left > right:
                inversions += 1
    return inversions


def _scene_cast(scene: dict[str, Any]) -> list[Any]:
    if "scene_cast" in scene:
        return scene.get("scene_cast") or []
    return scene.get("characters") or []


def score_schedule(
    days: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    location_weight: float = 1.0,
    cast_weight: float = 1.0,
    sequence_weight: float = 1.0,
) -> dict[str, float]:
    """Score a schedule. Lower score means better plan."""

    scene_by_id = _scene_lookup(scenes)
    ordered_scene_ids = _flatten_scene_ids(days)

    ordered_locations: list[str] = []
    for scene_id in ordered_scene_ids:
        scene = scene_by_id.get(scene_id, {})
        ordered_locations.append(str(scene.get("location") or ""))

    location_changes = 0
    for index in range(1, len(ordered_locations)):
        if ordered_locations[index] != ordered_locations[index - 1]:
            location_changes += 1

    location_blocks: dict[str, int] = {}
    previous_location: str | None = None
    for location in ordered_locations:
        if location != previous_location:
            location_blocks[location] = location_blocks.get(location, 0) + 1
            previous_location = location

    location_fragmentation = sum(
        max(0, blocks - 1)
        for blocks in location_blocks.values()
    )

    location_days: dict[str, list[int]] = {}
    for day_index, day in enumerate(days, start=1):
        seen_today: set[str] = set()
        for scene_id in day.get("scene_ids", []):
            location = str(scene_by_id.get(int(scene_id), {}).get("location") or "")
            if location in seen_today:
                continue
            seen_today.add(location)
            location_days.setdefault(location, []).append(day_index)

    location_non_consecutive_days = 0
    for day_indexes in location_days.values():
        for index in range(1, len(day_indexes)):
            if day_indexes[index] != day_indexes[index - 1] + 1:
                location_non_consecutive_days += 1

    location_cost = float(
        location_changes + location_fragmentation + location_non_consecutive_days
    )

    character_days: dict[str, list[int]] = {}
    for day_index, day in enumerate(days, start=1):
        seen_characters_today: set[str] = set()
        for scene_id in day.get("scene_ids", []):
            scene = scene_by_id.get(int(scene_id), {})
            for character in _scene_cast(scene):
                name = str(character or "").strip()
                if not name or name in seen_characters_today:
                    continue
                seen_characters_today.add(name)
                character_days.setdefault(name, []).append(day_index)

    cast_non_consecutive_days = 0
    for day_indexes in character_days.values():
        unique_days = sorted(set(day_indexes))
        for index in range(1, len(unique_days)):
            if unique_days[index] != unique_days[index - 1] + 1:
                cast_non_consecutive_days += 1

    cast_cost = float(cast_non_consecutive_days)

    sequence_keys: list[tuple[int, int]] = []
    for scene_id in ordered_scene_ids:
        scene = scene_by_id.get(scene_id, {})
        script_order = int(scene.get("script_order") or 0)
        sequence_keys.append((script_order, int(scene_id)))

    sequence_cost = float(_count_inversions(sequence_keys))

    total_score = (
        float(location_weight) * location_cost
        + float(cast_weight) * cast_cost
        + float(sequence_weight) * sequence_cost
    )

    return {
        "total_score": float(total_score),
        "location_cost": location_cost,
        "cast_cost": cast_cost,
        "sequence_cost": sequence_cost,
    }
