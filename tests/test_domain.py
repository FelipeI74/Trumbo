import unittest

from app.domain import estimate_runtime, format_seconds


class RuntimeTests(unittest.TestCase):
    def test_empty_scene_has_zero_runtime(self):
        self.assertEqual(estimate_runtime("").seconds, 0)

    def test_runtime_is_never_negative(self):
        self.assertEqual(format_seconds(-20), "00:00")

    def test_short_scene_has_minimum_runtime(self):
        self.assertGreaterEqual(estimate_runtime("MARTA entra.").seconds, 3)

    def test_format_seconds(self):
        self.assertEqual(format_seconds(125), "02:05")


if __name__ == "__main__":
    unittest.main()
