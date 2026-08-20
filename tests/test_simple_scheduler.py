import unittest

from app.scheduling.simple_scheduler import generate_schedule


class SimpleSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        # Fixture base de 6 escenas (Radio 6) sin dependencias externas.
        self.radio6_scenes = [
            {"scene_id": 70, "scene_number": 1, "script_order": 1, "location": "AUTO", "runtime_seconds": 150},
            {"scene_id": 71, "scene_number": 2, "script_order": 2, "location": "CASA DE CÁCERES", "runtime_seconds": 29},
            {"scene_id": 72, "scene_number": 3, "script_order": 3, "location": "SALA DE CONTROL", "runtime_seconds": 135},
            {"scene_id": 73, "scene_number": 4, "script_order": 4, "location": "AUTO", "runtime_seconds": 10},
            {"scene_id": 74, "scene_number": 5, "script_order": 5, "location": "SALA DE CONTROL", "runtime_seconds": 115},
            {"scene_id": 75, "scene_number": 6, "script_order": 6, "location": "EDIFICIO RADIO", "runtime_seconds": 118},
        ]

    def test_unique_assignment(self):
        result = generate_schedule(self.radio6_scenes, shoot_rate_seconds=420)

        assigned = [scene_id for day in result["days"] for scene_id in day["scene_ids"]]
        self.assertEqual(len(assigned), len(self.radio6_scenes))
        self.assertEqual(set(assigned), {scene["scene_id"] for scene in self.radio6_scenes})

    def test_runtime_sum_is_conserved(self):
        result = generate_schedule(self.radio6_scenes, shoot_rate_seconds=420)

        self.assertEqual(
            result["total_runtime_seconds"],
            sum(scene["runtime_seconds"] for scene in self.radio6_scenes),
        )

    def test_capacity_respected_except_over_capacity(self):
        result = generate_schedule(self.radio6_scenes, shoot_rate_seconds=420)

        for day in result["days"]:
            if day["over_capacity"]:
                self.assertGreater(day["runtime_seconds"], 420)
                self.assertEqual(len(day["scene_ids"]), 1)
            else:
                self.assertLessEqual(day["runtime_seconds"], 420)

    def test_locations_are_consecutive(self):
        result = generate_schedule(self.radio6_scenes, shoot_rate_seconds=420)

        scene_to_location = {
            scene["scene_id"]: scene["location"]
            for scene in self.radio6_scenes
        }
        ordered_locations = [
            scene_to_location[scene_id]
            for day in result["days"]
            for scene_id in day["scene_ids"]
        ]

        seen_blocks = []
        for location in ordered_locations:
            if not seen_blocks or seen_blocks[-1] != location:
                seen_blocks.append(location)

        self.assertEqual(seen_blocks, ["AUTO", "CASA DE CÁCERES", "SALA DE CONTROL", "EDIFICIO RADIO"])

    def test_deterministic_output(self):
        result_a = generate_schedule(self.radio6_scenes, shoot_rate_seconds=420)
        result_b = generate_schedule(list(reversed(self.radio6_scenes)), shoot_rate_seconds=420)

        self.assertEqual(result_a, result_b)

    def test_single_scene_over_capacity_goes_alone(self):
        scenes = [
            {"scene_id": 1, "scene_number": 1, "script_order": 1, "location": "A", "runtime_seconds": 100},
            {"scene_id": 2, "scene_number": 2, "script_order": 2, "location": "A", "runtime_seconds": 500},
            {"scene_id": 3, "scene_number": 3, "script_order": 3, "location": "B", "runtime_seconds": 80},
        ]

        result = generate_schedule(scenes, shoot_rate_seconds=420)

        over_days = [day for day in result["days"] if day["over_capacity"]]
        self.assertEqual(len(over_days), 1)
        self.assertEqual(over_days[0]["scene_ids"], [2])
        self.assertEqual(over_days[0]["locations"], ["A"])

    def test_empty_input(self):
        result = generate_schedule([], shoot_rate_seconds=420)

        self.assertEqual(result, {"days": [], "total_days": 0, "total_runtime_seconds": 0})


if __name__ == "__main__":
    unittest.main()
