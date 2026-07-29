import unittest

from app.domain import (
    ScriptElementType,
    estimate_runtime,
    format_seconds,
    is_character_cue,
    is_scene_heading,
    parse_screenplay,
    screenplay_summary,
)


class RuntimeTests(unittest.TestCase):
    def test_empty_scene_has_zero_runtime(self):
        self.assertEqual(estimate_runtime("").seconds, 0)

    def test_runtime_is_never_negative(self):
        self.assertEqual(format_seconds(-20), "00:00")

    def test_short_scene_has_minimum_runtime(self):
        self.assertGreaterEqual(estimate_runtime("MARTA entra.").seconds, 3)

    def test_format_seconds(self):
        self.assertEqual(format_seconds(125), "02:05")


class ScreenplayParserTests(unittest.TestCase):
    def test_recognizes_common_scene_headings(self):
        self.assertTrue(is_scene_heading("INT. COCINA - NOCHE"))
        self.assertTrue(is_scene_heading("EXT. PLAYA - DÍA"))
        self.assertTrue(is_scene_heading("INT/EXT. AUTO - NOCHE"))

    def test_character_cue_does_not_confuse_heading(self):
        self.assertTrue(is_character_cue("MARTA"))
        self.assertTrue(is_character_cue("PEDRO (V.O.)"))
        self.assertFalse(is_character_cue("INT. COCINA - NOCHE"))

    def test_parses_basic_scene_structure(self):
        body = "MARTA abre el cajón.\n\nPEDRO\n(en voz baja)\n¿La encontraste?\n\nCORTE A:"
        elements = [e for e in parse_screenplay("INT. COCINA - NOCHE", body) if e.type != ScriptElementType.EMPTY]
        self.assertEqual(
            [element.type for element in elements],
            [
                ScriptElementType.HEADING,
                ScriptElementType.ACTION,
                ScriptElementType.CHARACTER,
                ScriptElementType.PARENTHETICAL,
                ScriptElementType.DIALOGUE,
                ScriptElementType.TRANSITION,
            ],
        )

    def test_summary_lists_unique_characters(self):
        body = "PEDRO\nHola.\n\nMARTA\nAdiós.\n\nPEDRO (V.O.)\nEspera."
        summary = screenplay_summary("INT. CASA - DÍA", body)
        self.assertEqual(summary["characters"], ["PEDRO", "MARTA"])
        self.assertEqual(summary["counts"]["character"], 3)


if __name__ == "__main__":
    unittest.main()
