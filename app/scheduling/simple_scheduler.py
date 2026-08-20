from __future__ import annotations

from typing import Any


def _finalize_day(days: list[dict[str, Any]], day_scenes: list[int], day_locations: list[str], day_runtime: int, shoot_rate_seconds: int) -> None:
    if not day_scenes:
        return

    days.append(
        {
            "day": len(days) + 1,
            "runtime_seconds": day_runtime,
            "scene_ids": list(day_scenes),
            "locations": list(day_locations),
            "over_capacity": day_runtime > shoot_rate_seconds,
        }
    )


def generate_schedule(scenes: list[dict[str, Any]], shoot_rate_seconds: int = 420) -> dict[str, Any]:
    """Generate a deterministic day schedule from scene metadata.

    Input scenes must include: scene_id, scene_number, script_order, location, runtime_seconds.
    The function is pure and does not perform any I/O.
    """

    if not scenes:
        return {
            "days": [],
            "total_days": 0,
            "total_runtime_seconds": 0,
        }

    ordered_scenes = sorted(
        scenes,
        key=lambda item: (
            int(item["script_order"]),
            int(item["scene_number"]),
            int(item["scene_id"]),
        ),
    )

    grouped: dict[str, list[dict[str, Any]]] = {}
    group_order: dict[str, int] = {}

    for scene in ordered_scenes:
        location = str(scene.get("location") or "").strip()
        if location not in grouped:
            grouped[location] = []
            group_order[location] = int(scene["script_order"])
        grouped[location].append(scene)

    ordered_locations = sorted(
        grouped.keys(),
        key=lambda location: (group_order[location], location.casefold()),
    )

    days: list[dict[str, Any]] = []
    day_scenes: list[int] = []
    day_locations: list[str] = []
    day_runtime = 0

    for location in ordered_locations:
        location_scenes = sorted(
            grouped[location],
            key=lambda item: (
                int(item["script_order"]),
                int(item["scene_number"]),
                int(item["scene_id"]),
            ),
        )

        for scene in location_scenes:
            scene_id = int(scene["scene_id"])
            runtime = int(scene.get("runtime_seconds") or 0)

            if runtime > shoot_rate_seconds:
                _finalize_day(
                    days,
                    day_scenes,
                    day_locations,
                    day_runtime,
                    shoot_rate_seconds,
                )
                day_scenes = []
                day_locations = []
                day_runtime = 0

                days.append(
                    {
                        "day": len(days) + 1,
                        "runtime_seconds": runtime,
                        "scene_ids": [scene_id],
                        "locations": [location],
                        "over_capacity": True,
                    }
                )
                continue

            if day_runtime + runtime > shoot_rate_seconds:
                _finalize_day(
                    days,
                    day_scenes,
                    day_locations,
                    day_runtime,
                    shoot_rate_seconds,
                )
                day_scenes = []
                day_locations = []
                day_runtime = 0

            day_scenes.append(scene_id)
            day_runtime += runtime

            if location not in day_locations:
                day_locations.append(location)

    _finalize_day(
        days,
        day_scenes,
        day_locations,
        day_runtime,
        shoot_rate_seconds,
    )

    return {
        "days": days,
        "total_days": len(days),
        "total_runtime_seconds": sum(int(scene.get("runtime_seconds") or 0) for scene in ordered_scenes),
    }
