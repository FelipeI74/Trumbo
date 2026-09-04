import unittest
from unittest.mock import patch

from app.scheduling.optimizer import (
    _reorder_schedule_day_night,
    _schedule_respects_day_night_order,
    optimize_schedule,
)


class OptimizerDayNightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenes = [
            {"scene_id": 1, "time_of_day": "DÍA", "location": "A", "runtime_seconds": 100},
            {"scene_id": 2, "time_of_day": "NOCHE", "location": "A", "runtime_seconds": 100},
            {"scene_id": 3, "time_of_day": "DÍA", "location": "A", "runtime_seconds": 100},
            {"scene_id": 4, "time_of_day": "NOCHE", "location": "A", "runtime_seconds": 100},
        ]

    def test_rejects_day_after_night(self):
        schedule = {"days": [{"day": 1, "scene_ids": [1, 2, 3]}]}

        self.assertFalse(_schedule_respects_day_night_order(schedule, self.scenes))

    def test_accepts_day_day_night_night(self):
        schedule = {"days": [{"day": 1, "scene_ids": [1, 3, 2, 4]}]}

        self.assertTrue(_schedule_respects_day_night_order(schedule, self.scenes))

    def test_reorders_day_night_day_to_day_day_night(self):
        schedule = {"days": [{"day": 1, "scene_ids": [1, 2, 3]}]}

        reordered = _reorder_schedule_day_night(schedule, self.scenes)

        self.assertEqual(reordered["days"][0]["scene_ids"], [1, 3, 2])

    def test_reordering_preserves_day_scene_ids(self):
        schedule = {
            "days": [
                {"day": 1, "scene_ids": [1, 2, 3]},
                {"day": 2, "scene_ids": [4]},
            ]
        }

        reordered = _reorder_schedule_day_night(schedule, self.scenes)

        self.assertEqual(
            [set(day["scene_ids"]) for day in reordered["days"]],
            [{1, 2, 3}, {4}],
        )
        self.assertEqual(
            sorted(scene_id for day in reordered["days"] for scene_id in day["scene_ids"]),
            [1, 2, 3, 4],
        )

    def test_reordering_tolerates_empty_and_unknown_time_of_day(self):
        scenes = [
            {"scene_id": 1, "time_of_day": "DÍA"},
            {"scene_id": 2, "time_of_day": ""},
            {"scene_id": 3, "time_of_day": "FUTURO"},
            {"scene_id": 4, "time_of_day": "NOCHE"},
        ]
        schedule = {"days": [{"day": 1, "scene_ids": [4, 2, 3, 1]}]}

        reordered = _reorder_schedule_day_night(schedule, scenes)

        self.assertEqual(reordered["days"][0]["scene_ids"], [2, 3, 1, 4])

    def test_ignores_empty_time_of_day(self):
        scenes = [
            {"scene_id": 1, "time_of_day": "DÍA"},
            {"scene_id": 2, "time_of_day": ""},
            {"scene_id": 3, "time_of_day": "NOCHE"},
        ]
        schedule = {"days": [{"day": 1, "scene_ids": [1, 2, 3]}]}

        self.assertTrue(
            _schedule_respects_day_night_order(schedule, scenes)
        )

    def test_valid_cp_sat_wins_over_invalid_candidate(self):
        candidate_result = {
            "best_schedule": {"days": [{"day": 1, "scene_ids": [1, 2, 3, 4]}]},
            "score": {"total_score": 0.0},
            "candidates_evaluated": 1,
        }
        cp_sat_schedule = {
            "days": [{"day": 1, "scene_ids": [1, 3, 2, 4]}],
            "solver_status": "FEASIBLE",
            "objective_value": 1.0,
            "best_objective_bound": 1.0,
        }

        with patch(
            "app.scheduling.optimizer._optimize_schedule_by_candidates",
            return_value=candidate_result,
        ), patch(
            "app.scheduling.optimizer.generate_cp_sat_schedule",
            return_value=cp_sat_schedule,
        ):
            result = optimize_schedule(self.scenes)

        self.assertEqual(result["engine"], "cp_sat")
        self.assertEqual(result["best_schedule"], cp_sat_schedule)

    def test_fallback_returns_reordered_candidate(self):
        candidate_result = {
            "best_schedule": {"days": [{"day": 1, "scene_ids": [1, 2, 3, 4]}]},
            "score": {"total_score": 0.0},
            "candidates_evaluated": 1,
        }

        with patch(
            "app.scheduling.optimizer._optimize_schedule_by_candidates",
            return_value=candidate_result,
        ), patch(
            "app.scheduling.optimizer.generate_cp_sat_schedule",
            side_effect=RuntimeError("solver failed"),
        ):
            result = optimize_schedule(self.scenes)

        self.assertEqual(result["engine"], "fallback")
        self.assertEqual(result["best_schedule"]["days"][0]["scene_ids"], [1, 3, 2, 4])
        self.assertTrue(_schedule_respects_day_night_order(result["best_schedule"], self.scenes))


if __name__ == "__main__":
    unittest.main()
