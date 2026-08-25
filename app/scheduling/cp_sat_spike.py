from __future__ import annotations

from typing import Any

from ortools.sat.python import cp_model

from app.scheduling.scoring import score_schedule


def _scene_key(scene: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(scene.get("script_order") or 0),
        int(scene.get("scene_number") or 0),
        int(scene.get("scene_id") or 0),
    )


def _sequence_key(scene: dict[str, Any]) -> tuple[int, int]:
    # Same ordering key score_schedule uses to count inversions.
    return (
        int(scene.get("script_order") or 0),
        int(scene.get("scene_id") or 0),
    )


def _scene_cast(scene: dict[str, Any]) -> set[str]:
    # Same normalization as score_schedule: strip only, case sensitive.
    raw_cast = scene.get("scene_cast") if "scene_cast" in scene else scene.get("characters")
    return {
        str(name or "").strip()
        for name in (raw_cast or [])
        if str(name or "").strip()
    }


def _day_locations(day_scenes: list[dict[str, Any]]) -> list[str]:
    locations: list[str] = []
    for scene in day_scenes:
        location = str(scene.get("location") or "")
        if location not in locations:
            locations.append(location)
    return locations


def _warm_start_day_by_scene_id(warm_start_schedule: Any) -> dict[int, int]:
    days = warm_start_schedule.get("days", []) if isinstance(warm_start_schedule, dict) else warm_start_schedule
    if not isinstance(days, list):
        return {}

    day_by_scene_id: dict[int, int] = {}
    for fallback_day_index, day in enumerate(days):
        if not isinstance(day, dict):
            continue
        try:
            day_index = int(day.get("day", fallback_day_index + 1)) - 1
        except (TypeError, ValueError):
            day_index = fallback_day_index
        for scene_id in day.get("scene_ids") or []:
            try:
                day_by_scene_id[int(scene_id)] = day_index
            except (TypeError, ValueError):
                continue
    return day_by_scene_id


def _normalized_cast_unavailability(
    cast_unavailability: dict[str, list[int]] | None,
) -> dict[str, set[int]]:
    if not cast_unavailability:
        return {}

    unavailable_days_by_character: dict[str, set[int]] = {}
    for name, days in cast_unavailability.items():
        key = str(name or "").strip().casefold()
        if not key:
            continue
        for day in days or []:
            try:
                day_index = int(day) - 1
            except (TypeError, ValueError):
                continue
            unavailable_days_by_character.setdefault(key, set()).add(day_index)
    return unavailable_days_by_character


def _normalized_location_unavailability(
    location_unavailability: dict[str, list[int]] | None,
) -> dict[str, set[int]]:
    if not location_unavailability:
        return {}

    unavailable_days_by_location: dict[str, set[int]] = {}
    for location, days in location_unavailability.items():
        key = str(location or "").strip().casefold()
        if not key:
            continue
        for day in days or []:
            try:
                day_index = int(day) - 1
            except (TypeError, ValueError):
                continue
            unavailable_days_by_location.setdefault(key, set()).add(day_index)
    return unavailable_days_by_location


def generate_cp_sat_schedule(
    scenes: list[dict[str, Any]],
    shoot_rate_seconds: int = 420,
    location_weight: float = 1.0,
    cast_weight: float = 1.0,
    sequence_weight: float = 1.0,
    max_time_seconds: float = 60.0,
    warm_start_schedule: dict[str, Any] | list[dict[str, Any]] | None = None,
    cast_unavailability: dict[str, list[int]] | None = None,
    location_unavailability: dict[str, list[int]] | None = None,
) -> dict[str, Any]:
    """CP-SAT spike minimizing the exact score_schedule objective.

    location_cost, cast_cost and sequence_cost are modelled with the same
    definitions used by score_schedule, so the solver optimizes the real
    weighted score instead of a proxy. Day count is the only tie-break and it
    is scaled so it can never change the optimal weighted score.
    """

    if not scenes:
        return {
            "days": [],
            "total_days": 0,
            "total_runtime_seconds": 0,
            "solver_status": None,
            "objective_value": None,
            "best_objective_bound": None,
            "costs": {
                "total_score": 0.0,
                "location_cost": 0.0,
                "cast_cost": 0.0,
                "sequence_cost": 0.0,
            },
        }

    ordered_scenes = sorted(scenes, key=_scene_key)
    n = len(ordered_scenes)
    capacity = int(shoot_rate_seconds)

    runtimes = [
        int(scene.get("runtime_seconds") or 0)
        for scene in ordered_scenes
    ]
    over_indexes = {
        i for i in range(n)
        if runtimes[i] > capacity
    }

    scene_locations = [
        str(scene.get("location") or "")
        for scene in ordered_scenes
    ]
    locations = sorted(set(scene_locations))
    scenes_by_location = {
        location: [i for i in range(n) if scene_locations[i] == location]
        for location in locations
    }

    characters = sorted(
        {
            name
            for scene in ordered_scenes
            for name in _scene_cast(scene)
        }
    )
    scenes_by_character = {
        name: [
            i for i in range(n)
            if name in _scene_cast(ordered_scenes[i])
        ]
        for name in characters
    }

    model = cp_model.CpModel()

    x = {
        (i, d): model.NewBoolVar(f"x_{i}_{d}")
        for i in range(n)
        for d in range(n)
    }
    y = {
        d: model.NewBoolVar(f"y_{d}")
        for d in range(n)
    }
    q = {
        (i, k): model.NewBoolVar(f"q_{i}_{k}")
        for i in range(n)
        for k in range(n)
    }

    unavailable_days_by_character = _normalized_cast_unavailability(cast_unavailability)
    unavailable_days_by_location = _normalized_location_unavailability(location_unavailability)
    for i, scene in enumerate(ordered_scenes):
        unavailable_days = set()
        for name in _scene_cast(scene):
            key = name.strip().casefold()
            unavailable_days.update(unavailable_days_by_character.get(key, set()))
        location_key = str(scene.get("location") or "").strip().casefold()
        unavailable_days.update(unavailable_days_by_location.get(location_key, set()))
        for d in unavailable_days:
            if 0 <= d < n:
                model.Add(x[(i, d)] == 0)

    for i in range(n):
        model.Add(sum(x[(i, d)] for d in range(n)) == 1)
        model.Add(sum(q[(i, k)] for k in range(n)) == 1)

    for k in range(n):
        model.Add(sum(q[(i, k)] for i in range(n)) == 1)

    for d in range(n):
        for i in range(n):
            model.Add(x[(i, d)] <= y[d])

        model.Add(sum(x[(i, d)] for i in range(n)) >= 1).OnlyEnforceIf(y[d])
        model.Add(sum(x[(i, d)] for i in range(n)) == 0).OnlyEnforceIf(y[d].Not())

        model.Add(
            sum(
                runtimes[i] * x[(i, d)]
                for i in range(n)
                if i not in over_indexes
            )
            <= capacity
        )

        for i in over_indexes:
            model.Add(sum(x[(j, d)] for j in range(n)) == 1).OnlyEnforceIf(x[(i, d)])

    for d in range(n - 1):
        model.Add(y[d] >= y[d + 1])

    day_of_scene = [
        model.NewIntVar(0, n - 1, f"day_{i}")
        for i in range(n)
    ]
    position_of_scene = [
        model.NewIntVar(0, n - 1, f"pos_{i}")
        for i in range(n)
    ]
    for i in range(n):
        model.Add(day_of_scene[i] == sum(d * x[(i, d)] for d in range(n)))
        model.Add(position_of_scene[i] == sum(k * q[(i, k)] for k in range(n)))

    # The flattened sequence must group scenes by day, days in ascending order.
    day_at_position = [
        model.NewIntVar(0, n - 1, f"day_at_{k}")
        for k in range(n)
    ]
    for k in range(n):
        for i in range(n):
            model.Add(day_at_position[k] == day_of_scene[i]).OnlyEnforceIf(q[(i, k)])
    for k in range(n - 1):
        model.Add(day_at_position[k] <= day_at_position[k + 1])

    def _block_starts(flags: list[cp_model.IntVar], label: str) -> list[cp_model.IntVar]:
        starts = []
        for index in range(len(flags)):
            start = model.NewBoolVar(f"start_{label}_{index}")
            if index == 0:
                model.Add(start == flags[0])
            else:
                model.Add(start <= flags[index])
                model.Add(start + flags[index - 1] <= 1)
                model.Add(start >= flags[index] - flags[index - 1])
            starts.append(start)
        return starts

    # location_changes = (sequence blocks) - 1, fragmentation = blocks - locations.
    location_sequence_starts = []
    for slot, location in enumerate(locations):
        indexes = scenes_by_location[location]
        occupies = []
        for k in range(n):
            flag = model.NewBoolVar(f"locpos_{slot}_{k}")
            model.Add(flag == sum(q[(i, k)] for i in indexes))
            occupies.append(flag)
        location_sequence_starts.extend(_block_starts(occupies, f"locpos_{slot}"))

    location_day_starts = []
    for slot, location in enumerate(locations):
        indexes = scenes_by_location[location]
        works = []
        for d in range(n):
            flag = model.NewBoolVar(f"locday_{slot}_{d}")
            model.AddMaxEquality(flag, [x[(i, d)] for i in indexes])
            works.append(flag)
        location_day_starts.extend(_block_starts(works, f"locday_{slot}"))

    cast_day_starts = []
    for slot, name in enumerate(characters):
        indexes = scenes_by_character[name]
        works = []
        for d in range(n):
            flag = model.NewBoolVar(f"castday_{slot}_{d}")
            model.AddMaxEquality(flag, [x[(i, d)] for i in indexes])
            works.append(flag)
        cast_day_starts.extend(_block_starts(works, f"castday_{slot}"))

    sequence_keys = [_sequence_key(scene) for scene in ordered_scenes]
    inversions = []
    for i in range(n):
        for j in range(i + 1, n):
            earlier = model.NewBoolVar(f"before_{i}_{j}")
            model.Add(position_of_scene[i] < position_of_scene[j]).OnlyEnforceIf(earlier)
            model.Add(position_of_scene[i] > position_of_scene[j]).OnlyEnforceIf(earlier.Not())

            inversion = model.NewBoolVar(f"inv_{i}_{j}")
            if sequence_keys[i] > sequence_keys[j]:
                model.Add(inversion == earlier)
            else:
                model.Add(inversion + earlier == 1)
            inversions.append(inversion)

    location_count = len(locations)
    character_count = len(characters)
    sequence_bound = (n * (n - 1)) // 2

    location_cost_var = model.NewIntVar(0, 3 * n, "location_cost")
    cast_cost_var = model.NewIntVar(0, max(1, n * character_count), "cast_cost")
    sequence_cost_var = model.NewIntVar(0, max(1, sequence_bound), "sequence_cost")

    model.Add(
        location_cost_var
        == 2 * sum(location_sequence_starts)
        + sum(location_day_starts)
        - 1
        - 2 * location_count
    )
    model.Add(cast_cost_var == sum(cast_day_starts) - character_count)
    model.Add(sequence_cost_var == (sum(inversions) if inversions else 0))

    days_expr = sum(y[d] for d in range(n))

    scale = 1000
    location_coeff = int(round(float(location_weight) * scale))
    cast_coeff = int(round(float(cast_weight) * scale))
    sequence_coeff = int(round(float(sequence_weight) * scale))

    weighted_score = (
        location_coeff * location_cost_var
        + cast_coeff * cast_cost_var
        + sequence_coeff * sequence_cost_var
    )

    # Day count only breaks ties: it is strictly smaller than one score unit.
    model.Minimize((n + 1) * weighted_score + days_expr)

    warm_start_day_by_scene_id = _warm_start_day_by_scene_id(warm_start_schedule)
    for i, scene in enumerate(ordered_scenes):
        hinted_day = warm_start_day_by_scene_id.get(int(scene.get("scene_id") or 0))
        if hinted_day is None or hinted_day < 0 or hinted_day >= n:
            continue
        for d in range(n):
            model.AddHint(x[(i, d)], int(d == hinted_day))

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = float(max_time_seconds)

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("CP-SAT could not find a feasible schedule")

    sequence_indexes = sorted(
        range(n),
        key=lambda i: int(solver.Value(position_of_scene[i])),
    )

    days: list[dict[str, Any]] = []
    current_day_index: int | None = None
    current_scenes: list[dict[str, Any]] = []

    def _flush() -> None:
        if not current_scenes:
            return
        runtime = sum(int(scene.get("runtime_seconds") or 0) for scene in current_scenes)
        days.append(
            {
                "day": len(days) + 1,
                "runtime_seconds": runtime,
                "scene_ids": [int(scene.get("scene_id")) for scene in current_scenes],
                "locations": _day_locations(current_scenes),
                "over_capacity": runtime > capacity,
            }
        )

    for i in sequence_indexes:
        day_index = int(solver.Value(day_of_scene[i]))
        if current_day_index is None or day_index != current_day_index:
            _flush()
            current_scenes = []
            current_day_index = day_index
        current_scenes.append(ordered_scenes[i])

    _flush()

    costs = {
        "location_cost": float(solver.Value(location_cost_var)),
        "cast_cost": float(solver.Value(cast_cost_var)),
        "sequence_cost": float(solver.Value(sequence_cost_var)),
    }
    costs["total_score"] = (
        float(location_weight) * costs["location_cost"]
        + float(cast_weight) * costs["cast_cost"]
        + float(sequence_weight) * costs["sequence_cost"]
    )

    reference = score_schedule(
        days,
        ordered_scenes,
        location_weight=location_weight,
        cast_weight=cast_weight,
        sequence_weight=sequence_weight,
    )
    for key in ("location_cost", "cast_cost", "sequence_cost"):
        if costs[key] != reference[key]:
            raise RuntimeError(
                f"CP-SAT {key} {costs[key]} does not match score_schedule {reference[key]}"
            )

    return {
        "days": days,
        "total_days": len(days),
        "total_runtime_seconds": sum(runtimes),
        "solver_status": solver.StatusName(status),
        "objective_value": solver.ObjectiveValue(),
        "best_objective_bound": solver.BestObjectiveBound(),
        "costs": {
            "total_score": float(reference["total_score"]),
            "location_cost": costs["location_cost"],
            "cast_cost": costs["cast_cost"],
            "sequence_cost": costs["sequence_cost"],
        },
    }
