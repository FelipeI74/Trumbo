import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.database as database
import app.main as main
from app.schemas import ProjectCreate, SceneCreate


class CharacterCueIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        patcher = patch.object(
            database,
            "DB_PATH",
            Path(temporary_directory.name) / "trumbo.db",
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        database.initialize()

        self.project = main.create_project(
            ProjectCreate(title="Integration", format="feature")
        )

    def _create_scene_with_characters(self, character_cues):
        """
        Crea una escena con lineas 'character' segun los textos dados.

        El heading va como primera linea de semantic_lines.
        """
        semantic_lines = [
            {"type": "heading", "text": "INT. TEST - DIA"},
        ]
        for cue_text in character_cues:
            semantic_lines.append({
                "type": "character",
                "text": cue_text,
            })
            semantic_lines.append({
                "type": "dialogue",
                "text": "Dummy dialogue.",
            })

        return main.create_scene(
            self.project["id"],
            SceneCreate(
                heading="INT. TEST - DIA",
                body="Accion de prueba.",
                semantic_lines=semantic_lines,
            ),
        )

    def _get_scheduling_input(self):
        return main._build_project_scheduling_input(self.project["id"])

    def test_list_characters_splits_combined_cue(self):
        self._create_scene_with_characters(["FRED/BARNEY"])

        result = main.list_project_characters(self.project["id"])
        names = sorted(c["name"] for c in result["characters"])
        self.assertEqual(names, ["BARNEY", "FRED"])

    def test_list_characters_keeps_voice_over_as_normal_character(self):
        self._create_scene_with_characters(["FRED (V.O.)"])

        result = main.list_project_characters(self.project["id"])
        names = [c["name"] for c in result["characters"]]
        self.assertEqual(names, ["FRED"])

    def test_scheduling_input_splits_combined_cue(self):
        self._create_scene_with_characters(["FRED/BARNEY"])

        scheduling = self._get_scheduling_input()
        scene = scheduling["scenes"][0]
        self.assertEqual(sorted(scene["characters"]), ["BARNEY", "FRED"])
        self.assertEqual(scene["voice_over_characters"], [])

    def test_scheduling_input_marks_voice_over(self):
        self._create_scene_with_characters(["FRED (V.O.)"])

        scheduling = self._get_scheduling_input()
        scene = scheduling["scenes"][0]
        self.assertEqual(scene["characters"], ["FRED"])
        self.assertEqual(scene["voice_over_characters"], ["FRED"])

    def test_scheduling_input_mixed_voice_and_non_voice(self):
        self._create_scene_with_characters(["FRED (V.O.) / BARNEY"])

        scheduling = self._get_scheduling_input()
        scene = scheduling["scenes"][0]
        self.assertEqual(sorted(scene["characters"]), ["BARNEY", "FRED"])
        self.assertEqual(scene["voice_over_characters"], ["FRED"])


if __name__ == "__main__":
    unittest.main()
