import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.database as database
import app.main as main
from app.schemas import ProjectCreate, SceneCreate


class AliasesInSchedulingTests(unittest.TestCase):
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
            ProjectCreate(title="Aliases in scheduling", format="feature")
        )

    def _create_scene(self, character_cue):
        return main.create_scene(
            self.project["id"],
            SceneCreate(
                heading="INT. TEST - DIA",
                body="Accion.",
                semantic_lines=[
                    {"type": "heading", "text": "INT. TEST - DIA"},
                    {"type": "character", "text": character_cue},
                    {"type": "dialogue", "text": "Hola."},
                ],
            ),
        )

    def _insert_alias(self, primary_name, alias_name):
        with database.connect() as conn:
            conn.execute(
                "INSERT INTO character_aliases (project_id, primary_name, alias_name) VALUES (?, ?, ?)",
                (self.project["id"], primary_name, alias_name),
            )

    def _get_scheduling(self):
        return main._build_project_scheduling_input(self.project["id"])

    # --- Tests base ---

    def test_no_aliases_keeps_original_names(self):
        self._create_scene("FELIPE AMADO")

        result = self._get_scheduling()
        scene = result["scenes"][0]
        self.assertEqual(scene["characters"], ["FELIPE AMADO"])

    def test_alias_resolves_in_characters(self):
        self._create_scene("DON FELIPE")
        self._insert_alias("FELIPE AMADO", "don felipe")

        result = self._get_scheduling()
        scene = result["scenes"][0]
        self.assertEqual(scene["characters"], ["FELIPE AMADO"])

    def test_alias_and_primary_unify_in_characters(self):
        # Escena 1: cue "FELIPE AMADO". Escena 2: cue "DON FELIPE".
        self._create_scene("FELIPE AMADO")
        self._create_scene("DON FELIPE")
        self._insert_alias("FELIPE AMADO", "don felipe")

        result = self._get_scheduling()
        # Las dos escenas deben tener characters = ["FELIPE AMADO"]
        self.assertEqual(result["scenes"][0]["characters"], ["FELIPE AMADO"])
        self.assertEqual(result["scenes"][1]["characters"], ["FELIPE AMADO"])

    def test_alias_resolves_in_scene_cast(self):
        self._create_scene("DON FELIPE")
        self._insert_alias("FELIPE AMADO", "don felipe")

        result = self._get_scheduling()
        scene = result["scenes"][0]
        # scene_cast debe contener el nombre resuelto
        self.assertIn("FELIPE AMADO", scene["scene_cast"])
        self.assertNotIn("DON FELIPE", scene["scene_cast"])

    def test_voice_over_alias_resolves(self):
        self._create_scene("DON FELIPE (V.O.)")
        self._insert_alias("FELIPE AMADO", "don felipe")

        result = self._get_scheduling()
        scene = result["scenes"][0]
        self.assertEqual(scene["characters"], ["FELIPE AMADO"])
        self.assertEqual(scene["voice_over_characters"], ["FELIPE AMADO"])


if __name__ == "__main__":
    unittest.main()
