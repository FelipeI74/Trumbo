import itertools
import unittest

from app.scheduling.cp_sat_spike import generate_cp_sat_schedule
from app.scheduling.scoring import score_schedule


class CpSatSpikeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenes = [
            {"scene_id": 1, "scene_number": 1, "script_order": 1, "location": "A", "runtime_seconds": 120, "characters": ["ANA"]},
            {"scene_id": 2, "scene_number": 2, "script_order": 2, "location": "B", "runtime_seconds": 120, "characters": ["BOB"]},
            {"scene_id": 3, "scene_number": 3, "script_order": 3, "location": "A", "runtime_seconds": 120, "characters": ["ANA", "CARLA"]},
            {"scene_id": 4, "scene_number": 4, "script_order": 4, "location": "C", "runtime_seconds": 120, "characters": ["BOB"]},
            {"scene_id": 5, "scene_number": 5, "script_order": 5, "location": "C", "runtime_seconds": 120, "characters": ["CARLA"]},
        ]

        self.brute_scenes = [
            {"scene_id": 1, "scene_number": 1, "script_order": 1, "location": "A", "runtime_seconds": 100, "characters": ["ANA"]},
            {"scene_id": 2, "scene_number": 2, "script_order": 2, "location": "B", "runtime_seconds": 100, "characters": ["BOB"]},
            {"scene_id": 3, "scene_number": 3, "script_order": 3, "location": "A", "runtime_seconds": 100, "characters": ["ANA"]},
            {"scene_id": 4, "scene_number": 4, "script_order": 4, "location": "B", "runtime_seconds": 100, "characters": ["BOB"]},
        ]

    def _flatten(self, schedule: dict) -> list[int]:
        return [scene_id for day in schedule["days"] for scene_id in day["scene_ids"]]

    def test_unique_assignment(self):
        schedule = generate_cp_sat_schedule(self.scenes, shoot_rate_seconds=240)
        flattened = self._flatten(schedule)

        self.assertEqual(len(flattened), len(self.scenes))
        self.assertEqual(set(flattened), {scene["scene_id"] for scene in self.scenes})

    def test_capacity_respected(self):
        schedule = generate_cp_sat_schedule(self.scenes, shoot_rate_seconds=240)

        for day in schedule["days"]:
            if day["over_capacity"]:
                self.assertEqual(len(day["scene_ids"]), 1)
                self.assertGreater(day["runtime_seconds"], 240)
            else:
                self.assertLessEqual(day["runtime_seconds"], 240)

    def test_reproducible(self):
        first = generate_cp_sat_schedule(self.scenes, shoot_rate_seconds=240)
        second = generate_cp_sat_schedule(self.scenes, shoot_rate_seconds=240)

        self.assertEqual(first, second)

    def _cast_cost(self, days: list[dict], scenes: list[dict]) -> float:
        return score_schedule(days, scenes)["cast_cost"]

    def _brute_force_best(
        self,
        scenes: list[dict],
        capacity: int,
        location_weight: float = 1.0,
        cast_weight: float = 1.0,
        sequence_weight: float = 1.0,
    ) -> dict[str, float]:
        """Exhaustive search over every ordering and every consecutive day split."""

        n = len(scenes)
        best = None

        for permutation in itertools.permutations(range(n)):
            for mask in range(1 << (n - 1)):
                groups: list[list[int]] = []
                current = [permutation[0]]

                for index in range(1, n):
                    if (mask >> (index - 1)) & 1:
                        groups.append(current)
                        current = []
                    current.append(permutation[index])

                groups.append(current)

                days = []
                valid = True

                for group in groups:
                    runtime = sum(int(scenes[i]["runtime_seconds"]) for i in group)
                    if runtime > capacity and len(group) > 1:
                        valid = False
                        break
                    days.append(
                        {
                            "day": len(days) + 1,
                            "runtime_seconds": runtime,
                            "scene_ids": [int(scenes[i]["scene_id"]) for i in group],
                        }
                    )

                if not valid:
                    continue

                scored = score_schedule(
                    days,
                    scenes,
                    location_weight=location_weight,
                    cast_weight=cast_weight,
                    sequence_weight=sequence_weight,
                )

                if best is None or scored["total_score"] < best["total_score"]:
                    best = scored

        assert best is not None
        return best

    def test_cast_cost_consecutive_days_is_zero(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "runtime_seconds": 100, "characters": ["ANA"]},
            {"scene_id": 2, "script_order": 2, "location": "B", "runtime_seconds": 100, "characters": ["ANA"]},
        ]
        days = [
            {"day": 1, "scene_ids": [1]},
            {"day": 2, "scene_ids": [2]},
        ]

        self.assertEqual(self._cast_cost(days, scenes), 0.0)

    def test_cast_cost_gap_between_days_one_and_three(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "runtime_seconds": 100, "characters": ["ANA"]},
            {"scene_id": 2, "script_order": 2, "location": "B", "runtime_seconds": 100, "characters": ["BOB"]},
            {"scene_id": 3, "script_order": 3, "location": "C", "runtime_seconds": 100, "characters": ["ANA"]},
        ]
        days = [
            {"day": 1, "scene_ids": [1]},
            {"day": 2, "scene_ids": [2]},
            {"day": 3, "scene_ids": [3]},
        ]

        self.assertEqual(self._cast_cost(days, scenes), 1.0)

    def test_cast_cost_two_consecutive_blocks_is_one(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "runtime_seconds": 100, "characters": ["ANA"]},
            {"scene_id": 2, "script_order": 2, "location": "A", "runtime_seconds": 100, "characters": ["ANA"]},
            {"scene_id": 3, "script_order": 3, "location": "B", "runtime_seconds": 100, "characters": ["BOB"]},
            {"scene_id": 4, "script_order": 4, "location": "B", "runtime_seconds": 100, "characters": ["BOB"]},
            {"scene_id": 5, "script_order": 5, "location": "C", "runtime_seconds": 100, "characters": ["ANA"]},
            {"scene_id": 6, "script_order": 6, "location": "C", "runtime_seconds": 100, "characters": ["ANA"]},
        ]
        days = [
            {"day": 1, "scene_ids": [1]},
            {"day": 2, "scene_ids": [2]},
            {"day": 3, "scene_ids": [3]},
            {"day": 4, "scene_ids": [4]},
            {"day": 5, "scene_ids": [5]},
            {"day": 6, "scene_ids": [6]},
        ]

        self.assertEqual(self._cast_cost(days, scenes), 1.0)

    def test_reported_costs_match_score_schedule(self):
        schedule = generate_cp_sat_schedule(self.scenes, shoot_rate_seconds=240)
        reference = score_schedule(schedule["days"], self.scenes)

        self.assertEqual(schedule["costs"]["location_cost"], reference["location_cost"])
        self.assertEqual(schedule["costs"]["cast_cost"], reference["cast_cost"])
        self.assertEqual(schedule["costs"]["sequence_cost"], reference["sequence_cost"])
        self.assertEqual(schedule["costs"]["total_score"], reference["total_score"])

    def test_reports_solver_diagnostics(self):
        schedule = generate_cp_sat_schedule(self.scenes, shoot_rate_seconds=240)

        self.assertIn(schedule["solver_status"], {"OPTIMAL", "FEASIBLE"})
        self.assertIsInstance(schedule["objective_value"], float)
        self.assertIsInstance(schedule["best_objective_bound"], float)

    def test_accepts_max_time_seconds(self):
        schedule = generate_cp_sat_schedule(
            self.scenes,
            shoot_rate_seconds=240,
            max_time_seconds=1.0,
        )

        self.assertIn(schedule["solver_status"], {"OPTIMAL", "FEASIBLE"})
        self.assertEqual(set(self._flatten(schedule)), {scene["scene_id"] for scene in self.scenes})

    def test_accepts_valid_warm_start_schedule(self):
        warm_start_schedule = {
            "days": [
                {"day": 1, "scene_ids": [1, 2]},
                {"day": 2, "scene_ids": [3, 4]},
                {"day": 3, "scene_ids": [5]},
            ]
        }

        schedule = generate_cp_sat_schedule(
            self.scenes,
            shoot_rate_seconds=240,
            warm_start_schedule=warm_start_schedule,
        )

        self.assertIn(schedule["solver_status"], {"OPTIMAL", "FEASIBLE"})
        self.assertEqual(set(self._flatten(schedule)), {scene["scene_id"] for scene in self.scenes})

    def test_cast_unavailability_blocks_scene_on_day(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "runtime_seconds": 100, "characters": ["ANA"]},
            {"scene_id": 2, "script_order": 2, "location": "B", "runtime_seconds": 100, "characters": ["BOB"]},
        ]

        schedule = generate_cp_sat_schedule(
            scenes,
            shoot_rate_seconds=100,
            cast_unavailability={"ANA": [1]},
        )

        self.assertNotIn(1, schedule["days"][0]["scene_ids"])

    def test_cast_unavailability_matches_normalized_names(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "runtime_seconds": 100, "characters": ["ANA"]},
            {"scene_id": 2, "script_order": 2, "location": "B", "runtime_seconds": 100, "characters": ["BOB"]},
        ]

        schedule = generate_cp_sat_schedule(
            scenes,
            shoot_rate_seconds=100,
            cast_unavailability={" ana ": [1]},
        )

        self.assertNotIn(1, schedule["days"][0]["scene_ids"])

    def test_cast_unavailability_can_make_problem_infeasible(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "runtime_seconds": 100, "characters": ["ANA"]},
        ]

        with self.assertRaises(RuntimeError):
            generate_cp_sat_schedule(
                scenes,
                shoot_rate_seconds=100,
                cast_unavailability={"ANA": [1]},
            )

    def test_empty_scenes_reports_no_solver_diagnostics(self):
        schedule = generate_cp_sat_schedule([], shoot_rate_seconds=240)

        self.assertIsNone(schedule["solver_status"])
        self.assertIsNone(schedule["objective_value"])
        self.assertIsNone(schedule["best_objective_bound"])

    def test_cast_cost_matches_brute_force_minimum(self):
        weights = {"location_weight": 0.0, "cast_weight": 1.0, "sequence_weight": 0.0}

        schedule = generate_cp_sat_schedule(
            self.brute_scenes, shoot_rate_seconds=200, **weights
        )
        best = self._brute_force_best(self.brute_scenes, 200, **weights)

        self.assertEqual(schedule["costs"]["cast_cost"], best["cast_cost"])

    def test_location_cost_matches_brute_force_minimum(self):
        weights = {"location_weight": 1.0, "cast_weight": 0.0, "sequence_weight": 0.0}

        schedule = generate_cp_sat_schedule(
            self.brute_scenes, shoot_rate_seconds=200, **weights
        )
        best = self._brute_force_best(self.brute_scenes, 200, **weights)

        self.assertEqual(schedule["costs"]["location_cost"], best["location_cost"])

    def test_sequence_cost_matches_brute_force_minimum(self):
        weights = {"location_weight": 0.0, "cast_weight": 0.0, "sequence_weight": 1.0}

        schedule = generate_cp_sat_schedule(
            self.brute_scenes, shoot_rate_seconds=200, **weights
        )
        best = self._brute_force_best(self.brute_scenes, 200, **weights)

        self.assertEqual(schedule["costs"]["sequence_cost"], best["sequence_cost"])
        self.assertEqual(schedule["costs"]["sequence_cost"], 0.0)

    def test_total_score_matches_brute_force_minimum(self):
        for weights in (
            {"location_weight": 1.0, "cast_weight": 1.0, "sequence_weight": 1.0},
            {"location_weight": 5.0, "cast_weight": 1.0, "sequence_weight": 1.0},
            {"location_weight": 1.0, "cast_weight": 5.0, "sequence_weight": 1.0},
            {"location_weight": 1.0, "cast_weight": 1.0, "sequence_weight": 5.0},
        ):
            with self.subTest(**weights):
                schedule = generate_cp_sat_schedule(
                    self.brute_scenes, shoot_rate_seconds=200, **weights
                )
                best = self._brute_force_best(self.brute_scenes, 200, **weights)

                self.assertEqual(
                    schedule["costs"]["total_score"], best["total_score"]
                )

    def test_cast_cost_is_zero_when_grouping_is_possible(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "runtime_seconds": 100, "characters": ["ANA"]},
            {"scene_id": 2, "script_order": 2, "location": "B", "runtime_seconds": 100, "characters": ["BOB"]},
            {"scene_id": 3, "script_order": 3, "location": "C", "runtime_seconds": 100, "characters": ["ANA"]},
            {"scene_id": 4, "script_order": 4, "location": "D", "runtime_seconds": 100, "characters": ["BOB"]},
        ]

        schedule = generate_cp_sat_schedule(
            scenes,
            shoot_rate_seconds=200,
            location_weight=0.0,
            cast_weight=1.0,
            sequence_weight=0.0,
        )

        self.assertEqual(self._cast_cost(schedule["days"], scenes), 0.0)

    def test_over_capacity_scene_stays_alone(self):
        scenes = self.scenes + [
            {
                "scene_id": 6,
                "scene_number": 6,
                "script_order": 6,
                "location": "D",
                "runtime_seconds": 900,
                "characters": ["ANA"],
            }
        ]

        schedule = generate_cp_sat_schedule(scenes, shoot_rate_seconds=240)
        flattened = self._flatten(schedule)

        self.assertEqual(sorted(flattened), [1, 2, 3, 4, 5, 6])

        for day in schedule["days"]:
            if 6 in day["scene_ids"]:
                self.assertEqual(day["scene_ids"], [6])
                self.assertTrue(day["over_capacity"])

    def test_empty_scenes(self):
        schedule = generate_cp_sat_schedule([], shoot_rate_seconds=240)

        self.assertEqual(schedule["days"], [])
        self.assertEqual(schedule["total_days"], 0)
        self.assertEqual(schedule["total_runtime_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
