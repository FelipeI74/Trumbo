from __future__ import annotations

from typing import Any

from .scoring import score_schedule
from .simple_scheduler import generate_schedule


def _scene_key(scene: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(scene.get("script_order") or 0),
        int(scene.get("scene_number") or 0),
        int(scene.get("scene_id") or 0),
    )


def _cast_signature(scene: dict[str, Any]) -> tuple[str, ...]:
    raw = scene.get("characters") or []
    normalized = sorted(
        {
            str(name).strip().casefold()
            for name in raw
            if str(name).strip()
        }
    )
    return tuple(normalized)


def _flatten_schedule_scene_ids(schedule: dict[str, Any]) -> list[int]:
    ids: list[int] = []
    for day in schedule.get("days", []):
        for scene_id in day.get("scene_ids", []):
            ids.append(int(scene_id))
    return ids


def _finalize_day(
    days: list[dict[str, Any]],
    day_scene_ids: list[int],
    day_runtime: int,
    day_locations: list[str],
    shoot_rate_seconds: int,
) -> None:
    if not day_scene_ids:
        return

    days.append(
        {
            "day": len(days) + 1,
            "runtime_seconds": int(day_runtime),
            "scene_ids": list(day_scene_ids),
            "locations": list(day_locations),
            "over_capacity": int(day_runtime) > int(shoot_rate_seconds),
        }
    )


def _build_schedule_from_order(
    ordered_scene_ids: list[int],
    scene_by_id: dict[int, dict[str, Any]],
    shoot_rate_seconds: int,
) -> dict[str, Any]:
    days: list[dict[str, Any]] = []
    day_scene_ids: list[int] = []
    day_runtime = 0
    day_locations: list[str] = []

    for scene_id in ordered_scene_ids:
        scene = scene_by_id[int(scene_id)]
        runtime = int(scene.get("runtime_seconds") or 0)
        location = str(scene.get("location") or "")

        if runtime > int(shoot_rate_seconds):
            _finalize_day(
                days,
                day_scene_ids,
                day_runtime,
                day_locations,
                shoot_rate_seconds,
            )
            day_scene_ids = []
            day_runtime = 0
            day_locations = []

            days.append(
                {
                    "day": len(days) + 1,
                    "runtime_seconds": runtime,
                    "scene_ids": [int(scene_id)],
                    "locations": [location],
                    "over_capacity": True,
                }
            )
            continue

        if day_scene_ids and day_runtime + runtime > int(shoot_rate_seconds):
            _finalize_day(
                days,
                day_scene_ids,
                day_runtime,
                day_locations,
                shoot_rate_seconds,
            )
            day_scene_ids = []
            day_runtime = 0
            day_locations = []

        day_scene_ids.append(int(scene_id))
        day_runtime += runtime
        if location not in day_locations:
            day_locations.append(location)

    _finalize_day(
        days,
        day_scene_ids,
        day_runtime,
        day_locations,
        shoot_rate_seconds,
    )

    return {
        "days": days,
        "total_days": len(days),
        "total_runtime_seconds": sum(
            int(scene_by_id[scene_id].get("runtime_seconds") or 0)
            for scene_id in ordered_scene_ids
        ),
    }


def _candidate_orders(
    scenes: list[dict[str, Any]],
    base_order: list[int],
) -> list[list[int]]:
    scene_by_id = {
        int(scene["scene_id"]): scene
        for scene in scenes
    }

    orders: list[list[int]] = []
    seen: set[tuple[int, ...]] = set()

    def add(order: list[int]) -> None:
        key = tuple(int(scene_id) for scene_id in order)
        if key in seen:
            return
        seen.add(key)
        orders.append(list(key))

    add(base_order)

    sequence_order = [
        int(scene["scene_id"])
        for scene in sorted(scenes, key=_scene_key)
    ]
    add(sequence_order)

    location_order = [
        int(scene["scene_id"])
        for scene in sorted(
            scenes,
            key=lambda scene: (
                str(scene.get("location") or "").casefold(),
                *_scene_key(scene),
            ),
        )
    ]
    add(location_order)

    cast_order = [
        int(scene["scene_id"])
        for scene in sorted(
            scenes,
            key=lambda scene: (
                _cast_signature(scene),
                *_scene_key(scene),
            ),
        )
    ]
    add(cast_order)

    add(list(reversed(sequence_order)))

    for index in range(len(base_order) - 1):
        swapped = list(base_order)
        swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
        add(swapped)

    for index in range(len(base_order)):
        moved_to_front = list(base_order)
        scene_id = moved_to_front.pop(index)
        moved_to_front.insert(0, scene_id)
        add(moved_to_front)

        moved_to_end = list(base_order)
        scene_id = moved_to_end.pop(index)
        moved_to_end.append(scene_id)
        add(moved_to_end)

    return orders


def optimize_schedule(
    scenes: list[dict[str, Any]],
    shoot_rate_seconds: int = 420,
    location_weight: float = 1.0,
    cast_weight: float = 1.0,
    sequence_weight: float = 1.0,
    search_depth: int = 20,
) -> dict[str, Any]:
    """Generate and score deterministic schedule alternatives; lower score is better."""

    base_schedule = generate_schedule(
        scenes,
        shoot_rate_seconds=shoot_rate_seconds,
    )
    base_order = _flatten_schedule_scene_ids(base_schedule)

    scene_by_id = {
        int(scene["scene_id"]): scene
        for scene in scenes
    }

    max_candidates = max(1, int(search_depth))
    candidate_orders = _candidate_orders(scenes, base_order)

    best_schedule: dict[str, Any] | None = None
    best_score: dict[str, float] | None = None
    evaluated = 0

    for order in candidate_orders[:max_candidates]:
        schedule = _build_schedule_from_order(
            order,
            scene_by_id,
            shoot_rate_seconds,
        )
        score = score_schedule(
            schedule["days"],
            scenes,
            location_weight=location_weight,
            cast_weight=cast_weight,
            sequence_weight=sequence_weight,
        )

        evaluated += 1

        if best_score is None or score["total_score"] < best_score["total_score"]:
            best_schedule = schedule
            best_score = score

    return {
        "best_schedule": best_schedule or base_schedule,
        "score": best_score or score_schedule(
            base_schedule.get("days", []),
            scenes,
            location_weight=location_weight,
            cast_weight=cast_weight,
            sequence_weight=sequence_weight,
        ),
        "candidates_evaluated": int(evaluated),
    }
