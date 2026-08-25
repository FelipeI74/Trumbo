from __future__ import annotations

from typing import Any

from .cp_sat_spike import generate_cp_sat_schedule
from .scoring import score_schedule
from .simple_scheduler import generate_schedule


def _scene_key(scene: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(scene.get("script_order") or 0),
        int(scene.get("scene_number") or 0),
        int(scene.get("scene_id") or 0),
    )


def _cast_signature(scene: dict[str, Any]) -> tuple[str, ...]:
    raw = scene.get("scene_cast") if "scene_cast" in scene else scene.get("characters")
    normalized = sorted(
        {
            str(name).strip().casefold()
            for name in (raw or [])
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


def _normalized_unavailability(
    unavailability: dict[str, list[int]] | None,
) -> dict[str, set[int]]:
    if not unavailability:
        return {}

    normalized: dict[str, set[int]] = {}
    for name, days in unavailability.items():
        key = str(name or "").strip().casefold()
        if not key:
            continue
        normalized[key] = {
            int(day)
            for day in (days or [])
            if isinstance(day, (int, str)) and str(day).strip().lstrip("-").isdigit()
        }
    return normalized


def _scene_cast(scene: dict[str, Any]) -> list[Any]:
    if "scene_cast" in scene:
        return scene.get("scene_cast") or []
    return scene.get("characters") or []


def _schedule_respects_hard_availability(
    schedule: dict[str, Any],
    scenes: list[dict[str, Any]],
    cast_unavailability: dict[str, list[int]] | None,
    location_unavailability: dict[str, list[int]] | None,
) -> bool:
    unavailable_cast = _normalized_unavailability(cast_unavailability)
    unavailable_locations = _normalized_unavailability(location_unavailability)
    if not unavailable_cast and not unavailable_locations:
        return True

    scenes_by_id = {int(scene["scene_id"]): scene for scene in scenes}
    for day in schedule.get("days", []):
        day_number = int(day.get("day", 0))
        for scene_id in day.get("scene_ids", []):
            scene = scenes_by_id.get(int(scene_id))
            if scene is None:
                return False

            location_key = str(scene.get("location") or "").strip().casefold()
            if day_number in unavailable_locations.get(location_key, set()):
                return False

            for character in _scene_cast(scene):
                character_key = str(character or "").strip().casefold()
                if day_number in unavailable_cast.get(character_key, set()):
                    return False

    return True


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


def _optimize_schedule_by_candidates(
    scenes: list[dict[str, Any]],
    shoot_rate_seconds: int = 420,
    location_weight: float = 1.0,
    cast_weight: float = 1.0,
    sequence_weight: float = 1.0,
    time_of_day_weight: float = 0.0,
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
            time_of_day_weight=time_of_day_weight,
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
            time_of_day_weight=time_of_day_weight,
        ),
        "candidates_evaluated": int(evaluated),
    }


def _with_engine_metadata(
    result: dict[str, Any],
    engine: str,
    fallback_used: bool,
    solver_status: str | None = None,
    objective_value: float | None = None,
    best_objective_bound: float | None = None,
) -> dict[str, Any]:
    return {
        **result,
        "engine": engine,
        "fallback_used": fallback_used,
        "solver_status": solver_status,
        "objective_value": objective_value,
        "best_objective_bound": best_objective_bound,
    }


def optimize_schedule(
    scenes: list[dict[str, Any]],
    shoot_rate_seconds: int = 420,
    location_weight: float = 1.0,
    cast_weight: float = 1.0,
    sequence_weight: float = 1.0,
    search_depth: int = 20,
    engine: str = "cp_sat",
    max_time_seconds: float = 60.0,
    cast_unavailability: dict[str, list[int]] | None = None,
    location_unavailability: dict[str, list[int]] | None = None,
    time_of_day_weight: float = 0.0,
) -> dict[str, Any]:
    """Optimize a schedule with CP-SAT by default and candidate search as fallback."""

    if engine == "candidates":
        candidate_result = _optimize_schedule_by_candidates(
            scenes,
            shoot_rate_seconds=shoot_rate_seconds,
            location_weight=location_weight,
            cast_weight=cast_weight,
            sequence_weight=sequence_weight,
            time_of_day_weight=time_of_day_weight,
            search_depth=search_depth,
        )
        if not _schedule_respects_hard_availability(
            candidate_result["best_schedule"],
            scenes,
            cast_unavailability,
            location_unavailability,
        ):
            raise RuntimeError(
                "Candidate schedule violates hard availability constraints"
            )
        return _with_engine_metadata(
            candidate_result,
            engine="candidates",
            fallback_used=False,
        )

    candidate_result = _optimize_schedule_by_candidates(
        scenes,
        shoot_rate_seconds=shoot_rate_seconds,
        location_weight=location_weight,
        cast_weight=cast_weight,
        sequence_weight=sequence_weight,
        time_of_day_weight=time_of_day_weight,
        search_depth=search_depth,
    )
    candidate_score = score_schedule(
        candidate_result["best_schedule"].get("days", []),
        scenes,
        location_weight=location_weight,
        cast_weight=cast_weight,
        sequence_weight=sequence_weight,
        time_of_day_weight=time_of_day_weight,
    )
    candidate_result = {
        **candidate_result,
        "score": candidate_score,
    }
    candidate_is_valid = _schedule_respects_hard_availability(
        candidate_result["best_schedule"],
        scenes,
        cast_unavailability,
        location_unavailability,
    )

    try:
        cp_sat_schedule = generate_cp_sat_schedule(
            scenes,
            shoot_rate_seconds=shoot_rate_seconds,
            location_weight=location_weight,
            cast_weight=cast_weight,
            sequence_weight=sequence_weight,
            max_time_seconds=max_time_seconds,
            warm_start_schedule=candidate_result["best_schedule"],
            cast_unavailability=cast_unavailability,
            location_unavailability=location_unavailability,
            time_of_day_weight=time_of_day_weight,
        )
        score = score_schedule(
            cp_sat_schedule.get("days", []),
            scenes,
            location_weight=location_weight,
            cast_weight=cast_weight,
            sequence_weight=sequence_weight,
            time_of_day_weight=time_of_day_weight,
        )

        solver_status = cp_sat_schedule.get("solver_status")
        objective_value = cp_sat_schedule.get("objective_value")
        best_objective_bound = cp_sat_schedule.get("best_objective_bound")

        if candidate_is_valid and candidate_score["total_score"] < score["total_score"]:
            return _with_engine_metadata(
                candidate_result,
                engine="candidates",
                fallback_used=False,
                solver_status=solver_status,
                objective_value=objective_value,
                best_objective_bound=best_objective_bound,
            )

        return {
            "best_schedule": cp_sat_schedule,
            "score": score,
            "candidates_evaluated": candidate_result["candidates_evaluated"],
            "engine": "cp_sat",
            "fallback_used": False,
            "solver_status": solver_status,
            "objective_value": objective_value,
            "best_objective_bound": best_objective_bound,
        }
    except Exception:
        if cast_unavailability is not None or location_unavailability is not None:
            raise RuntimeError(
                "CP-SAT could not satisfy hard availability constraints"
            )
        return _with_engine_metadata(
            candidate_result,
            engine="fallback",
            fallback_used=True,
        )
