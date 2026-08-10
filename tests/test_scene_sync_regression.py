import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.database as database
import app.main as main
from app.schemas import ProjectCreate, SceneCreate, SceneUpdate


class SceneSyncRegressionTests(unittest.TestCase):
    def _prepare_empty_database(self, tmpdir: str) -> None:
        db_path = Path(tmpdir) / "trumbo.db"

        patcher = patch.object(database, "DB_PATH", db_path)
        patcher.start()
        self.addCleanup(patcher.stop)

        database.initialize()

        with database.connect() as connection:
            connection.execute("DELETE FROM scenes")
            connection.execute("DELETE FROM projects")

    def test_new_project_has_zero_scenes_without_heading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            created = main.create_project(
                ProjectCreate(title="Proyecto vacío", format="feature")
            )

            payload = main.get_project(created["id"])

            self.assertEqual(payload["project"]["id"], created["id"])
            self.assertEqual(payload["scenes"], [])

    def test_three_headings_map_to_three_scenes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            created = main.create_project(
                ProjectCreate(title="Tres escenas", format="feature")
            )

            headings = [
                "INT. CASA - DIA",
                "EXT. CALLE - NOCHE",
                "INT. AUTO - DIA",
            ]

            for heading in headings:
                main.create_scene(
                    created["id"],
                    SceneCreate(
                        heading=heading,
                        body="Acción de prueba",
                    ),
                )

            payload = main.get_project(created["id"])

            self.assertEqual(len(payload["scenes"]), 3)
            self.assertEqual(
                [scene["heading"] for scene in payload["scenes"]],
                headings,
            )

    def test_editing_heading_updates_corresponding_scene(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            created = main.create_project(
                ProjectCreate(title="Editar heading", format="feature")
            )

            scene = main.create_scene(
                created["id"],
                SceneCreate(
                    heading="INT. CASA DE JUAN - DIA",
                    body="Juan entra.",
                ),
            )

            main.update_scene(
                scene["id"],
                SceneUpdate(
                    heading="INT. CASA DE PEDRO - NOCHE",
                ),
            )

            payload = main.get_project(created["id"])

            self.assertEqual(
                payload["scenes"][0]["heading"],
                "INT. CASA DE PEDRO - NOCHE",
            )

    def test_clearing_heading_removes_stale_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            created = main.create_project(
                ProjectCreate(title="Borrar heading", format="feature")
            )

            original_heading = "INT. CASA DE PEDRO - DIA"

            scene = main.create_scene(
                created["id"],
                SceneCreate(
                    heading=original_heading,
                    body="Pedro entra.",
                ),
            )

            main.update_scene(
                scene["id"],
                SceneUpdate(heading=""),
            )

            payload = main.get_project(created["id"])

            self.assertEqual(payload["scenes"][0]["heading"], "")
            self.assertNotEqual(
                payload["scenes"][0]["heading"],
                original_heading,
            )

    def test_delete_scene_renumbers_remaining_scenes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            created = main.create_project(
                ProjectCreate(title="Eliminar escena", format="feature")
            )

            first = main.create_scene(
                created["id"],
                SceneCreate(
                    heading="INT. CASA - DIA",
                    body="Acción 1",
                ),
            )

            second = main.create_scene(
                created["id"],
                SceneCreate(
                    heading="EXT. CALLE - NOCHE",
                    body="Acción 2",
                ),
            )

            third = main.create_scene(
                created["id"],
                SceneCreate(
                    heading="INT. AUTO - DIA",
                    body="Acción 3",
                ),
            )

            self.assertEqual(first["scene_number"], 1)
            self.assertEqual(second["scene_number"], 2)
            self.assertEqual(third["scene_number"], 3)

            main.delete_scene(second["id"])

            payload = main.get_project(created["id"])

            self.assertEqual(len(payload["scenes"]), 2)
            self.assertEqual(
                [scene["scene_number"] for scene in payload["scenes"]],
                [1, 2],
            )
            self.assertEqual(
                [scene["heading"] for scene in payload["scenes"]],
                [
                    "INT. CASA - DIA",
                    "INT. AUTO - DIA",
                ],
            )


if __name__ == "__main__":
    unittest.main()
