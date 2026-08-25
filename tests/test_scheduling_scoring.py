import unittest

from app.scheduling.scoring import score_schedule


class SchedulingScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "characters": ["ANA"]},
            {"scene_id": 2, "script_order": 2, "location": "A", "characters": ["ANA", "BOB"]},
            {"scene_id": 3, "script_order": 3, "location": "B", "characters": ["BOB"]},
            {"scene_id": 4, "script_order": 4, "location": "B", "characters": ["ANA"]},
        ]

    def test_same_plan_same_weights_same_score(self):
        days = [
            {"day": 1, "scene_ids": [1, 2]},
            {"day": 2, "scene_ids": [3, 4]},
        ]

        score_a = score_schedule(days, self.scenes, 1.0, 1.0, 1.0)
        score_b = score_schedule(days, self.scenes, 1.0, 1.0, 1.0)

        self.assertEqual(score_a, score_b)

    def test_grouped_locations_improve_location_cost(self):
        grouped_days = [
            {"day": 1, "scene_ids": [1, 2]},
            {"day": 2, "scene_ids": [3, 4]},
        ]
        split_days = [
            {"day": 1, "scene_ids": [1, 3]},
            {"day": 2, "scene_ids": [2, 4]},
        ]

        grouped_score = score_schedule(grouped_days, self.scenes)
        split_score = score_schedule(split_days, self.scenes)

        self.assertLess(grouped_score["location_cost"], split_score["location_cost"])

    def test_grouped_cast_improves_cast_cost(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "characters": ["ANA"]},
            {"scene_id": 2, "script_order": 2, "location": "B", "characters": ["BOB"]},
            {"scene_id": 3, "script_order": 3, "location": "C", "characters": ["ANA"]},
        ]

        grouped_days = [
            {"day": 1, "scene_ids": [1, 3]},
            {"day": 2, "scene_ids": [2]},
        ]
        split_days = [
            {"day": 1, "scene_ids": [1]},
            {"day": 2, "scene_ids": [2]},
            {"day": 3, "scene_ids": [3]},
        ]

        grouped_score = score_schedule(grouped_days, scenes)
        split_score = score_schedule(split_days, scenes)

        self.assertLess(grouped_score["cast_cost"], split_score["cast_cost"])

    def test_scene_cast_overrides_characters_for_cast_cost(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "characters": [], "scene_cast": ["MUDO"]},
            {"scene_id": 2, "script_order": 2, "location": "B", "characters": [], "scene_cast": []},
            {"scene_id": 3, "script_order": 3, "location": "C", "characters": [], "scene_cast": ["MUDO"]},
        ]
        days = [
            {"day": 1, "scene_ids": [1]},
            {"day": 2, "scene_ids": [2]},
            {"day": 3, "scene_ids": [3]},
        ]

        self.assertEqual(score_schedule(days, scenes)["cast_cost"], 1.0)

    def test_cast_cost_falls_back_to_characters_without_scene_cast(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "characters": ["ANA"]},
            {"scene_id": 2, "script_order": 2, "location": "B", "characters": ["BOB"]},
            {"scene_id": 3, "script_order": 3, "location": "C", "characters": ["ANA"]},
        ]
        days = [
            {"day": 1, "scene_ids": [1]},
            {"day": 2, "scene_ids": [2]},
            {"day": 3, "scene_ids": [3]},
        ]

        self.assertEqual(score_schedule(days, scenes)["cast_cost"], 1.0)

    def test_same_time_of_day_has_zero_cost(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "time_of_day": "DÍA"},
            {"scene_id": 2, "script_order": 2, "location": "B", "time_of_day": "DIA"},
        ]
        days = [{"day": 1, "scene_ids": [1, 2]}]

        self.assertEqual(score_schedule(days, scenes)["time_of_day_cost"], 0.0)

    def test_day_to_night_has_one_change(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "time_of_day": "DÍA"},
            {"scene_id": 2, "script_order": 2, "location": "B", "time_of_day": "NOCHE"},
        ]
        days = [{"day": 1, "scene_ids": [1, 2]}]

        self.assertEqual(score_schedule(days, scenes)["time_of_day_cost"], 1.0)

    def test_amanecer_and_atarceder_are_distinct(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "time_of_day": "AMANECER"},
            {"scene_id": 2, "script_order": 2, "location": "B", "time_of_day": "ATARDECER"},
        ]
        days = [{"day": 1, "scene_ids": [1, 2]}]

        self.assertEqual(score_schedule(days, scenes)["time_of_day_cost"], 1.0)

    def test_empty_time_of_day_values_are_ignored(self):
        scenes = [
            {"scene_id": 1, "script_order": 1, "location": "A", "time_of_day": "DÍA"},
            {"scene_id": 2, "script_order": 2, "location": "B", "time_of_day": ""},
            {"scene_id": 3, "script_order": 3, "location": "C", "time_of_day": "NOCHE"},
        ]
        days = [{"day": 1, "scene_ids": [1, 2, 3]}]

        self.assertEqual(score_schedule(days, scenes)["time_of_day_cost"], 1.0)

    def test_narrative_order_improves_sequence_cost(self):
        ordered_days = [
            {"day": 1, "scene_ids": [1, 2, 3, 4]},
        ]
        shuffled_days = [
            {"day": 1, "scene_ids": [2, 1, 4, 3]},
        ]

        ordered_score = score_schedule(ordered_days, self.scenes)
        shuffled_score = score_schedule(shuffled_days, self.scenes)

        self.assertLess(ordered_score["sequence_cost"], shuffled_score["sequence_cost"])

    def test_changing_weights_changes_total_only(self):
        days = [
            {"day": 1, "scene_ids": [1, 3]},
            {"day": 2, "scene_ids": [2, 4]},
        ]

        score_default = score_schedule(days, self.scenes, 1.0, 1.0, 1.0)
        score_weighted = score_schedule(days, self.scenes, 5.0, 2.0, 3.0)

        self.assertEqual(score_default["location_cost"], score_weighted["location_cost"])
        self.assertEqual(score_default["cast_cost"], score_weighted["cast_cost"])
        self.assertEqual(score_default["sequence_cost"], score_weighted["sequence_cost"])
        self.assertNotEqual(score_default["total_score"], score_weighted["total_score"])

    def test_zero_weight_removes_criterion_from_total(self):
        days = [
            {"day": 1, "scene_ids": [1, 3]},
            {"day": 2, "scene_ids": [2, 4]},
        ]

        score_with_zero_location = score_schedule(
            days,
            self.scenes,
            location_weight=0.0,
            cast_weight=1.0,
            sequence_weight=1.0,
        )

        expected_total = (
            score_with_zero_location["cast_cost"]
            + score_with_zero_location["sequence_cost"]
        )

        self.assertEqual(score_with_zero_location["total_score"], expected_total)


if __name__ == "__main__":
    unittest.main()
