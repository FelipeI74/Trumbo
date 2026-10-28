import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.database as database
import app.main as main
from app.schemas import ProjectCreate, SceneCreate


class CharacterAliasesIntegrationTests(unittest.TestCase):
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
            ProjectCreate(title="Alias integration", format="feature")
        )

    def _create_scene_with_characters(self, character_cues):
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

    def _insert_alias(self, primary_name, alias_name):
        with database.connect() as conn:
            conn.execute(
                "INSERT INTO character_aliases (project_id, primary_name, alias_name) VALUES (?, ?, ?)",
                (self.project["id"], primary_name, alias_name),
            )

    def test_no_aliases_returns_names_unchanged(self):
        self._create_scene_with_characters(["FELIPE AMADO", "MARTA"])

        result = main.list_project_characters(self.project["id"])
        names = sorted(c["name"] for c in result["characters"])
        self.assertEqual(names, ["FELIPE AMADO", "MARTA"])

    def test_single_alias_resolves_to_primary(self):
        self._create_scene_with_characters(["DON FELIPE"])
        self._insert_alias("FELIPE AMADO", "don felipe")

        result = main.list_project_characters(self.project["id"])
        names = [c["name"] for c in result["characters"]]
        self.assertEqual(names, ["FELIPE AMADO"])

    def test_alias_and_primary_unify_to_single_character(self):
        self._create_scene_with_characters(["FELIPE AMADO", "DON FELIPE"])
        self._insert_alias("FELIPE AMADO", "don felipe")

        result = main.list_project_characters(self.project["id"])
        names = [c["name"] for c in result["characters"]]
        self.assertEqual(names, ["FELIPE AMADO"])
        # Debe aparecer una sola vez, no dos
        self.assertEqual(len(names), 1)

    def test_multiple_aliases_to_same_primary_unify(self):
        self._create_scene_with_characters(["DON FELIPE", "PIPE", "FELIPE A."])
        self._insert_alias("FELIPE AMADO", "don felipe")
        self._insert_alias("FELIPE AMADO", "pipe")
        self._insert_alias("FELIPE AMADO", "felipe a.")

        result = main.list_project_characters(self.project["id"])
        names = [c["name"] for c in result["characters"]]
        self.assertEqual(names, ["FELIPE AMADO"])

    def test_alias_in_combined_cue_resolves(self):
        self._create_scene_with_characters(["DON FELIPE/MARTA"])
        self._insert_alias("FELIPE AMADO", "don felipe")

        result = main.list_project_characters(self.project["id"])
        names = sorted(c["name"] for c in result["characters"])
        self.assertEqual(names, ["FELIPE AMADO", "MARTA"])

    def test_alias_in_voice_over_cue_resolves(self):
        self._create_scene_with_characters(["DON FELIPE (V.O.)"])
        self._insert_alias("FELIPE AMADO", "don felipe")

        result = main.list_project_characters(self.project["id"])
        names = [c["name"] for c in result["characters"]]
        self.assertEqual(names, ["FELIPE AMADO"])

    def test_scene_numbers_are_merged_across_aliases(self):
        # Escena 1: DON FELIPE. Escena 2: FELIPE AMADO. Deben unificarse.
        self._create_scene_with_characters(["DON FELIPE"])
        self._create_scene_with_characters(["FELIPE AMADO"])
        self._insert_alias("FELIPE AMADO", "don felipe")

        result = main.list_project_characters(self.project["id"])
        self.assertEqual(len(result["characters"]), 1)
        character = result["characters"][0]
        self.assertEqual(character["name"], "FELIPE AMADO")
        self.assertEqual(character["scene_count"], 2)
        self.assertEqual(character["scene_numbers"], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
