import unittest

from app.scheduling.optimizer import optimize_schedule


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

    def test_candidates_evaluated_respects_search_depth(self):
        result = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=5)

        self.assertLessEqual(result["candidates_evaluated"], 5)

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
        result = optimize_schedule(self.scenes, shoot_rate_seconds=300, search_depth=1)

        flattened = self._flatten(result["best_schedule"])
        expected = [scene["scene_id"] for scene in self.scenes]

        self.assertEqual(set(flattened), set(expected))
        self.assertEqual(result["candidates_evaluated"], 1)


if __name__ == "__main__":
    unittest.main()
