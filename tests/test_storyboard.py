import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.database as database
import app.main as main
from app.schemas import (
    ProjectCreate,
    SceneCreate,
    ShotCreate,
    ShotReorderRequest,
    ShotUpdate,
)


class StoryboardTests(unittest.TestCase):
    def _prepare_empty_database(self, tmpdir: str) -> None:
        db_path = Path(tmpdir) / "trumbo.db"

        patcher = patch.object(database, "DB_PATH", db_path)
        patcher.start()
        self.addCleanup(patcher.stop)

        database.initialize()

    def _create_project_and_scene(self):
        project = main.create_project(
            ProjectCreate(
                title="Storyboard Test",
                format="feature",
            )
        )

        scene = main.create_scene(
            project["id"],
            SceneCreate(
                heading="INT. CASA - DIA",
                body="MARTA entra.",
            ),
        )

        return project, scene

    def test_create_list_update_reorder_delete_shots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, scene = self._create_project_and_scene()

            first = main.create_shot(
                project["id"],
                scene["id"],
                ShotCreate(
                    shot_type="PM",
                    description="Plano uno",
                ),
            )

            second = main.create_shot(
                project["id"],
                scene["id"],
                ShotCreate(
                    shot_type="PP",
                    description="Plano dos",
                ),
            )

            shots = main.list_shots(
                project["id"],
                scene["id"],
            )
            self.assertEqual(len(shots), 2)

            updated = main.update_shot_metadata(
                project["id"],
                first["id"],
                ShotUpdate(
                    description="Descripción actualizada"
                ),
            )
            self.assertEqual(
                updated["description"],
                "Descripción actualizada",
            )

            main.reorder_shots(
                project["id"],
                scene["id"],
                ShotReorderRequest(
                    shot_ids=[
                        second["id"],
                        first["id"],
                    ]
                ),
            )

            shots = main.list_shots(
                project["id"],
                scene["id"],
            )
            self.assertEqual(
                shots[0]["id"],
                second["id"],
            )
            self.assertEqual(
                shots[0]["sort_order"],
                1,
            )

            main.delete_shot(
                project["id"],
                first["id"],
            )

            shots = main.list_shots(
                project["id"],
                scene["id"],
            )
            self.assertEqual(len(shots), 1)


if __name__ == "__main__":
    unittest.main()
    