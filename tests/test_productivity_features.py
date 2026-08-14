import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.database as database
import app.main as main
from app.schemas import BreakdownItemCreate, BreakdownItemUpdate, ProjectCreate, SceneCreate


class ProductivityFeaturesTests(unittest.TestCase):
    def _prepare_empty_database(self, tmpdir: str) -> None:
        db_path = Path(tmpdir) / "trumbo.db"

        patcher = patch.object(database, "DB_PATH", db_path)
        patcher.start()
        self.addCleanup(patcher.stop)

        database.initialize()

        with database.connect() as connection:
            connection.execute("DELETE FROM breakdown_items")
            connection.execute("DELETE FROM scenes")
            connection.execute("DELETE FROM projects")

    def test_scene_spelling_review_returns_misspellings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Ortografia", format="feature")
            )

            scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. CASA - DIA",
                    body="El perssonaje camina y luego saluuda.",
                ),
            )

            review = main.scene_spelling_review(scene["id"])

            self.assertEqual(review["scene_id"], scene["id"])
            self.assertGreater(review["total_words"], 0)
            self.assertTrue(
                any(
                    item["word"] in {"perssonaje", "saluuda"}
                    for item in review["misspellings"]
                )
            )

    def test_project_pdf_export_returns_stream(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Export PDF", format="feature")
            )

            main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. CASA - NOCHE",
                    body="Linea de prueba para exportar.",
                ),
            )

            response = main.export_project_pdf(project["id"])

            self.assertEqual(response.media_type, "application/pdf")
            self.assertIn("Content-Disposition", response.headers)

    def test_project_pdf_uses_screenplay_geometry_and_paginates_without_loss(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Guion largo", format="feature")
            )
            long_action = "Accion esperada " * 900
            main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. CASA - NOCHE",
                    body=long_action,
                    semantic_lines=[
                        {"type": "heading", "text": "INT. CASA - NOCHE"},
                        {"type": "character", "text": "MARTA"},
                        {"type": "parenthetical", "text": "(susurra)"},
                        {"type": "dialogue", "text": "No podemos quedarnos aqui."},
                        {"type": "transition", "text": "CORTE A:"},
                        {"type": "action", "text": long_action},
                    ],
                ),
            )

            response = main.export_project_pdf(project["id"])

            async def read_stream():
                return b"".join([chunk async for chunk in response.body_iterator])

            pdf_bytes = asyncio.run(read_stream())
            self.assertGreaterEqual(pdf_bytes.count(b"/Type /Page"), 2)
            self.assertIn(b"MARTA", pdf_bytes)
            self.assertIn(b"No podemos quedarnos aqui.", pdf_bytes)
            self.assertIn(b"CORTE A:", pdf_bytes)
            self.assertIn(b"Accion esperada", pdf_bytes)

    def test_breakdown_item_can_change_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Desglose", format="feature")
            )

            scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. TALLER - DIA",
                    body="Hay una bicicleta y un martillo.",
                ),
            )

            created = main.add_breakdown_item(
                scene["id"],
                BreakdownItemCreate(
                    category="prop",
                    name="Bicicleta",
                    source="manual",
                    state="detected",
                ),
            )

            updated = main.update_breakdown_item(
                created["id"],
                BreakdownItemUpdate(state="confirmed"),
            )

            self.assertEqual(updated["id"], created["id"])
            self.assertEqual(updated["state"], "confirmed")

            listed = main.list_scene_breakdown(
                scene["id"],
                category="prop",
                state="confirmed",
            )

            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["id"], created["id"])


if __name__ == "__main__":
    unittest.main()
