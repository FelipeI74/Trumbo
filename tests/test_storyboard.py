import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

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

    def test_scene_delete_cascades_shots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, scene = self._create_project_and_scene()

            shot = main.create_shot(
                project["id"],
                scene["id"],
                ShotCreate(shot_type="PM"),
            )

            with database.connect() as connection:
                connection.execute(
                    "DELETE FROM scenes WHERE id = ?",
                    (scene["id"],),
                )
                connection.commit()

                remaining = connection.execute(
                    "SELECT id FROM shots WHERE id = ?",
                    (shot["id"],),
                ).fetchone()

            self.assertIsNone(remaining)

    def test_storyboard_storage_image_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = main.StoryboardStorage(
                base_dir=tmpdir
            )

            storage_key = "1/shots/test-shot.png"
            image_data = b"fake-png-data"

            storage.save_image(
                storage_key,
                image_data,
            )

            loaded = storage.read_image(storage_key)

            self.assertEqual(
                loaded,
                image_data,
            )

            deleted = storage.delete_image(storage_key)

            self.assertTrue(deleted)

            with self.assertRaises(FileNotFoundError):
                storage.read_image(storage_key)

    def test_upload_shot_image_rejects_non_image_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, scene = self._create_project_and_scene()
            shot = main.create_shot(
                project["id"],
                scene["id"],
                ShotCreate(shot_type="PM"),
            )
            request = type(
                "RequestStub",
                (),
                {"body": AsyncMock(return_value=b"not-an-image")},
            )()

            with self.assertRaises(HTTPException) as context:
                asyncio.run(
                    main.upload_shot_image(project["id"], shot["id"], request)
                )

            self.assertEqual(context.exception.status_code, 400)

    def test_upload_shot_image_rejects_images_over_10_mb(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, scene = self._create_project_and_scene()
            shot = main.create_shot(
                project["id"],
                scene["id"],
                ShotCreate(shot_type="PM"),
            )
            image_data = b"\x89PNG\r\n\x1a\n" + b"x" * (10 * 1024 * 1024)
            request = type(
                "RequestStub",
                (),
                {"body": AsyncMock(return_value=image_data)},
            )()

            with self.assertRaises(HTTPException) as context:
                asyncio.run(
                    main.upload_shot_image(project["id"], shot["id"], request)
                )

            self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()