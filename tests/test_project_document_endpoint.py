import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import app.database as database
import app.main as main
from app.schemas import ProjectCreate, SceneCreate


class ProjectDocumentEndpointTests(unittest.TestCase):
    def _prepare_empty_database(self, tmpdir: str) -> None:
        db_path = Path(tmpdir) / "trumbo.db"

        patcher = patch.object(database, "DB_PATH", db_path)
        patcher.start()
        self.addCleanup(patcher.stop)

        database.initialize()

        with database.connect() as connection:
            connection.execute("DELETE FROM document_lines")
            connection.execute("DELETE FROM documents")
            connection.execute("DELETE FROM breakdown_items")
            connection.execute("DELETE FROM notes")
            connection.execute("DELETE FROM revisions")
            connection.execute("DELETE FROM scenes")
            connection.execute("DELETE FROM projects")

    def _create_project_with_two_scenes(self) -> tuple[dict, dict, dict]:
        project = main.create_project(
            ProjectCreate(title="Document endpoint", format="feature")
        )

        first = main.create_scene(
            project["id"],
            SceneCreate(
                heading="INT. CASA - DIA",
                body="MARTA entra.",
                synopsis="Marta llega a casa.",
                semantic_lines=[
                    {"type": "heading", "text": "INT. CASA - DIA"},
                    {"type": "action", "text": "MARTA entra."},
                ],
            ),
        )

        second = main.create_scene(
            project["id"],
            SceneCreate(
                heading="EXT. CALLE - NOCHE",
                body="PEDRO espera.",
                synopsis="Pedro espera en la calle.",
                semantic_lines=[
                    {"type": "heading", "text": "EXT. CALLE - NOCHE"},
                    {"type": "action", "text": "PEDRO espera."},
                ],
            ),
        )

        main.add_note(first["id"], payload=type("NotePayload", (), {"category": "general", "body": "Nota escena 1"})())
        main.add_breakdown_item(
            first["id"],
            payload=type(
                "BreakdownPayload",
                (),
                {
                    "category": "props",
                    "name": "Llave",
                    "source": "manual",
                    "state": "confirmed",
                },
            )(),
        )

        return project, first, second

    def test_1_returns_document_and_lines_ordered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, _, _ = self._create_project_with_two_scenes()

            payload = main.get_project_document(project["id"])

            self.assertEqual(payload["project"]["id"], project["id"])
            self.assertEqual(payload["document"]["project_id"], project["id"])

            lines = payload["lines"]
            self.assertEqual(len(lines), 4)

            self.assertEqual(
                [line["text"] for line in lines],
                [
                    "INT. CASA - DIA",
                    "MARTA entra.",
                    "EXT. CALLE - NOCHE",
                    "PEDRO espera.",
                ],
            )

            for line in lines:
                self.assertEqual(
                    sorted(line.keys()),
                    [
                        "source_line_index",
                        "source_scene_id",
                        "text",
                        "type",
                        "uuid",
                    ],
                )

    def test_2_3_4_5_parity_with_legacy_scenes_when_projection_is_bijective(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, _, _ = self._create_project_with_two_scenes()

            legacy = main.get_project(project["id"])
            documental = main.get_project_document(project["id"])

            legacy_scenes = legacy["scenes"]
            derived_scenes = documental["derived_scenes"]

            self.assertEqual(len(derived_scenes), len(legacy_scenes))
            self.assertEqual(
                [scene["scene_number"] for scene in derived_scenes],
                [scene["scene_number"] for scene in legacy_scenes],
            )
            self.assertEqual(
                [scene["id"] for scene in derived_scenes],
                [scene["id"] for scene in legacy_scenes],
            )

            for left, right in zip(derived_scenes, legacy_scenes):
                self.assertEqual(left["heading"], right["heading"])
                self.assertEqual(left["body"], right["body"])
                self.assertEqual(left["semantic_lines"], right["semantic_lines"])
                self.assertEqual(left["synopsis"], right["synopsis"])
                self.assertEqual(left["runtime_seconds"], right["runtime_seconds"])
                self.assertEqual(left["notes"], right["notes"])
                self.assertEqual(left["breakdown_items"], right["breakdown_items"])

            self.assertEqual(documental["inconsistencies"], [])

    def test_6_empty_project_with_document_returns_zero_derived_scenes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Empty with doc", format="feature")
            )

            created_scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. TEMP - DIA",
                    body="Temporal",
                ),
            )

            main.delete_scene(created_scene["id"])

            payload = main.get_project_document(project["id"])

            self.assertEqual(payload["document"]["project_id"], project["id"])
            self.assertEqual(payload["lines"], [])
            self.assertEqual(payload["derived_scenes"], [])

    def test_7_fade_in_preface_stays_in_lines_and_does_not_create_scene(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, first, _ = self._create_project_with_two_scenes()

            with database.connect() as connection:
                document_id = connection.execute(
                    "SELECT id FROM documents WHERE project_id = ?",
                    (project["id"],),
                ).fetchone()["id"]

                connection.execute(
                    "UPDATE document_lines SET position = position + 1000 WHERE document_id = ?",
                    (document_id,),
                )

                connection.execute(
                    "UPDATE document_lines SET position = position - 999 WHERE document_id = ?",
                    (document_id,),
                )

                connection.execute(
                    """
                    INSERT INTO document_lines(
                        uuid,
                        document_id,
                        position,
                        type,
                        text,
                        source_scene_id,
                        source_line_index
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "preface-fade-in",
                        document_id,
                        0,
                        "transition",
                        "FADE IN:",
                        first["id"],
                        None,
                    ),
                )

            payload = main.get_project_document(project["id"])

            self.assertEqual(payload["lines"][0]["text"], "FADE IN:")
            self.assertEqual(payload["derived_scenes"][0]["heading"], "INT. CASA - DIA")
            self.assertEqual(len(payload["derived_scenes"]), 2)

    def test_8_detects_mixed_source_scene_id_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, _, second = self._create_project_with_two_scenes()

            with database.connect() as connection:
                document_id = connection.execute(
                    "SELECT id FROM documents WHERE project_id = ?",
                    (project["id"],),
                ).fetchone()["id"]

                connection.execute(
                    """
                    UPDATE document_lines
                    SET source_scene_id = ?
                    WHERE document_id = ? AND position = 1
                    """,
                    (second["id"], document_id),
                )

            payload = main.get_project_document(project["id"])

            conflicted = payload["derived_scenes"][0]
            self.assertIsNone(conflicted["id"])
            self.assertTrue(conflicted["structural_conflict"])
            self.assertIsNone(conflicted["synopsis"])
            self.assertEqual(conflicted["notes"], [])
            self.assertEqual(conflicted["breakdown_items"], [])

            self.assertTrue(payload["inconsistencies"])

    def test_9_legacy_project_endpoint_keeps_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, _, _ = self._create_project_with_two_scenes()

            payload = main.get_project(project["id"])

            self.assertIn("project", payload)
            self.assertIn("scenes", payload)
            self.assertEqual(len(payload["scenes"]), 2)
            self.assertIn("notes", payload["scenes"][0])
            self.assertIn("breakdown_items", payload["scenes"][0])

    def test_10_returns_404_if_project_has_no_document(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="No document", format="feature")
            )

            with self.assertRaises(HTTPException) as context:
                main.get_project_document(project["id"])

            self.assertEqual(context.exception.status_code, 404)
            self.assertEqual(
                context.exception.detail,
                "El proyecto aún no tiene un documento generado. Guarda una escena para crearlo.",
            )


if __name__ == "__main__":
    unittest.main()
