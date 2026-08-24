import unittest
from unittest.mock import patch

from app.scheduling.optimizer import optimize_schedule
from app.scheduling.scoring import score_schedule


class SchedulingOptimizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenes = [
            {"scene_id": 1, "scene_number": 1, "script_order": 1, "location": "A", "runtime_seconds": 150, "characters": ["X"]},
            {"scene_id": 2, "scene_number": 2, "script_order": 2, "location": "B", "runtime_seconds": 150, "characters": ["Y"]},
            {"scene_id": 3, "scene_number": 3, "script_order": 3, "location": "C", "runtime_seconds": 150, "characters": ["X"]},
            {"scene_id": 4, "scene_number": 4, "script_order": 4, "location": "A", "runtime_seconds": 150, "characters": ["Z"]},
            {"scene_id": 5, "scene_number": 5, "script_order": 5, "location": "B", "runtime_seconds": 150, "characters": ["Y"]},
            {"scene_id": 6, "scene_number": 6, "script_order": 6, "location": "C", "runtime_seconds": 150, "characters": ["Z"]},
        ]

    def _flatten(self, schedule: dict) -> list[int]:
        return [scene_id for day in schedule["days"] for scene_id in day["scene_ids"]]

    def test_never_loses_or_duplicates_scenes(self):
        result = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=20)

        flattened = self._flatten(result["best_schedule"])
        expected = [scene["scene_id"] for scene in self.scenes]

        self.assertEqual(len(flattened), len(expected))
        self.assertEqual(set(flattened), set(expected))

    def test_respects_capacity_except_over_capacity_singletons(self):
        scenes = self.scenes + [
            {"scene_id": 99, "scene_number": 99, "script_order": 99, "location": "D", "runtime_seconds": 500, "characters": ["W"]}
        ]

        result = optimize_schedule(scenes, shoot_rate_seconds=300, search_depth=20)

        for day in result["best_schedule"]["days"]:
            if day["over_capacity"]:
                self.assertGreater(day["runtime_seconds"], 300)
                self.assertEqual(len(day["scene_ids"]), 1)
            else:
                self.assertLessEqual(day["runtime_seconds"], 300)

    def test_is_deterministic(self):
        result_a = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=20)
        result_b = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=20)

        self.assertEqual(result_a, result_b)

    def test_existing_call_contract_is_preserved(self):
        result = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=20)

        self.assertIn("best_schedule", result)
        self.assertIn("score", result)
        self.assertIn("candidates_evaluated", result)
        self.assertIn("days", result["best_schedule"])
        self.assertIn("total_score", result["score"])

    def test_cp_sat_can_win_as_primary_engine(self):
        cp_sat_schedule = {
            "days": [
                {"day": 1, "runtime_seconds": 300, "scene_ids": [1, 4], "locations": ["A"], "over_capacity": False},
                {"day": 2, "runtime_seconds": 300, "scene_ids": [2, 5], "locations": ["B"], "over_capacity": False},
                {"day": 3, "runtime_seconds": 300, "scene_ids": [3, 6], "locations": ["C"], "over_capacity": False},
            ],
            "total_days": 3,
            "total_runtime_seconds": 900,
            "solver_status": "OPTIMAL",
            "objective_value": 3.0,
            "best_objective_bound": 3.0,
        }

        with patch(
            "app.scheduling.optimizer.generate_cp_sat_schedule",
            return_value=cp_sat_schedule,
        ):
            result = optimize_schedule(
                self.scenes,
                shoot_rate_seconds=300,
                location_weight=1.0,
                cast_weight=0.0,
                sequence_weight=0.0,
                search_depth=1,
            )

        self.assertEqual(result["engine"], "cp_sat")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["solver_status"], "OPTIMAL")
        self.assertEqual(result["objective_value"], 3.0)
        self.assertEqual(result["best_objective_bound"], 3.0)

    def test_default_uses_cp_sat_when_not_worse_than_candidates(self):
        result = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=20)

        self.assertIn(result["engine"], {"cp_sat", "candidates"})
        self.assertFalse(result["fallback_used"])
        self.assertIn(result["solver_status"], {"OPTIMAL", "FEASIBLE"})
        self.assertIsInstance(result["objective_value"], float)
        self.assertIsInstance(result["best_objective_bound"], float)

    def test_default_never_returns_worse_score_than_candidates(self):
        default_result = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=20)
        candidate_result = optimize_schedule(
            self.scenes,
            shoot_rate_seconds=300,
            search_depth=20,
            engine="candidates",
        )

        self.assertLessEqual(
            default_result["score"]["total_score"],
            candidate_result["score"]["total_score"],
        )

    def test_candidate_wins_when_cp_sat_score_is_worse(self):
        worse_cp_sat_schedule = {
            "days": [
                {"day": 1, "runtime_seconds": 300, "scene_ids": [1, 3], "locations": ["A", "C"], "over_capacity": False},
                {"day": 2, "runtime_seconds": 300, "scene_ids": [2, 5], "locations": ["B"], "over_capacity": False},
                {"day": 3, "runtime_seconds": 300, "scene_ids": [4, 6], "locations": ["A", "C"], "over_capacity": False},
            ],
            "total_days": 3,
            "total_runtime_seconds": 900,
            "solver_status": "FEASIBLE",
            "objective_value": 99.0,
            "best_objective_bound": 1.0,
        }

        with patch(
            "app.scheduling.optimizer.generate_cp_sat_schedule",
            return_value=worse_cp_sat_schedule,
        ):
            result = optimize_schedule(
                self.scenes,
                shoot_rate_seconds=300,
                location_weight=1.0,
                cast_weight=0.0,
                sequence_weight=0.0,
                search_depth=20,
            )

        self.assertEqual(result["engine"], "candidates")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["solver_status"], "FEASIBLE")
        self.assertEqual(result["objective_value"], 99.0)
        self.assertEqual(result["best_objective_bound"], 1.0)

    def test_cp_sat_uses_candidate_schedule_as_warm_start(self):
        with patch(
            "app.scheduling.optimizer.generate_cp_sat_schedule",
            side_effect=RuntimeError("stop after inspecting warm start"),
        ) as generate_cp_sat:
            result = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=5)

        self.assertEqual(result["engine"], "fallback")
        self.assertEqual(
            generate_cp_sat.call_args.kwargs["warm_start_schedule"],
            result["best_schedule"],
        )

    def test_passes_cast_unavailability_to_cp_sat(self):
        cast_unavailability = {"X": [1]}
        with patch(
            "app.scheduling.optimizer.generate_cp_sat_schedule",
            side_effect=RuntimeError("stop after inspecting availability"),
        ) as generate_cp_sat:
            with self.assertRaisesRegex(RuntimeError, "cast availability"):
                optimize_schedule(
                    self.scenes,
                    shoot_rate_seconds=300,
                    cast_unavailability=cast_unavailability,
                )

        self.assertEqual(
            generate_cp_sat.call_args.kwargs["cast_unavailability"],
            cast_unavailability,
        )

    def test_cast_unavailability_failure_does_not_fallback_to_candidates(self):
        with patch(
            "app.scheduling.optimizer.generate_cp_sat_schedule",
            side_effect=RuntimeError("infeasible"),
        ):
            with self.assertRaisesRegex(RuntimeError, "cast availability"):
                optimize_schedule(
                    self.scenes,
                    shoot_rate_seconds=300,
                    search_depth=5,
                    cast_unavailability={"X": [1]},
                )

    def test_score_is_coherent_with_common_scoring(self):
        result = optimize_schedule(
            self.scenes,
            shoot_rate_seconds=300,
            location_weight=2.0,
            cast_weight=3.0,
            sequence_weight=4.0,
        )
        expected = score_schedule(
            result["best_schedule"]["days"],
            self.scenes,
            location_weight=2.0,
            cast_weight=3.0,
            sequence_weight=4.0,
        )

        self.assertEqual(result["score"], expected)

    def test_candidates_evaluated_respects_search_depth(self):
        result = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=5, engine="candidates")

        self.assertLessEqual(result["candidates_evaluated"], 5)

    def test_engine_candidates_uses_previous_optimizer(self):
        result = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=5, engine="candidates")

        self.assertEqual(result["engine"], "candidates")
        self.assertFalse(result["fallback_used"])
        self.assertGreater(result["candidates_evaluated"], 0)
        self.assertIsNone(result["solver_status"])

    def test_cp_sat_exception_falls_back_to_candidates(self):
        with patch(
            "app.scheduling.optimizer.generate_cp_sat_schedule",
            side_effect=RuntimeError("solver failed"),
        ):
            result = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=5)

        self.assertEqual(result["engine"], "fallback")
        self.assertTrue(result["fallback_used"])
        self.assertGreater(result["candidates_evaluated"], 0)
        self.assertIsNone(result["solver_status"])

    def test_high_location_weight_favors_better_location_cost(self):
        location_dominant = optimize_schedule(
            self.scenes,
            shoot_rate_seconds=300,
            location_weight=100.0,
            cast_weight=1.0,
            sequence_weight=1.0,
            search_depth=20,
        )
        cast_dominant = optimize_schedule(
            self.scenes,
            shoot_rate_seconds=300,
            location_weight=1.0,
            cast_weight=100.0,
            sequence_weight=1.0,
            search_depth=20,
        )
        sequence_dominant = optimize_schedule(
            self.scenes,
            shoot_rate_seconds=300,
            location_weight=1.0,
            cast_weight=1.0,
            sequence_weight=100.0,
            search_depth=20,
        )

        self.assertLessEqual(location_dominant["score"]["location_cost"], cast_dominant["score"]["location_cost"])
        self.assertLessEqual(location_dominant["score"]["location_cost"], sequence_dominant["score"]["location_cost"])

    def test_high_cast_weight_favors_better_cast_cost(self):
        location_dominant = optimize_schedule(
            self.scenes,
            shoot_rate_seconds=300,
            location_weight=100.0,
            cast_weight=1.0,
            sequence_weight=1.0,
            search_depth=20,
        )
        cast_dominant = optimize_schedule(
            self.scenes,
            shoot_rate_seconds=300,
            location_weight=1.0,
            cast_weight=100.0,
            sequence_weight=1.0,
            search_depth=20,
        )
        sequence_dominant = optimize_schedule(
            self.scenes,
            shoot_rate_seconds=300,
            location_weight=1.0,
            cast_weight=1.0,
            sequence_weight=100.0,
            search_depth=20,
        )

        self.assertLessEqual(cast_dominant["score"]["cast_cost"], location_dominant["score"]["cast_cost"])
        self.assertLessEqual(cast_dominant["score"]["cast_cost"], sequence_dominant["score"]["cast_cost"])

    def test_high_sequence_weight_favors_better_sequence_cost(self):
        location_dominant = optimize_schedule(
            self.scenes,
            shoot_rate_seconds=300,
            location_weight=100.0,
            cast_weight=1.0,
            sequence_weight=1.0,
            search_depth=20,
        )
        cast_dominant = optimize_schedule(
            self.scenes,
            shoot_rate_seconds=300,
            location_weight=1.0,
            cast_weight=100.0,
            sequence_weight=1.0,
            search_depth=20,
        )
        sequence_dominant = optimize_schedule(
            self.scenes,
            shoot_rate_seconds=300,
            location_weight=1.0,
            cast_weight=1.0,
            sequence_weight=100.0,
            search_depth=20,
        )

        self.assertLessEqual(sequence_dominant["score"]["sequence_cost"], location_dominant["score"]["sequence_cost"])
        self.assertLessEqual(sequence_dominant["score"]["sequence_cost"], cast_dominant["score"]["sequence_cost"])

    def test_search_depth_one_returns_valid_solution(self):
        result = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=1, engine="candidates")

        flattened = self._flatten(result["best_schedule"])
        expected = [scene["scene_id"] for scene in self.scenes]

        self.assertEqual(set(flattened), set(expected))
        self.assertEqual(result["candidates_evaluated"], 1)


if __name__ == "__main__":
    unittest.main()
