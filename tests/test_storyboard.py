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

    def test_storyboard_storage_rejects_paths_outside_base_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "assets"
            storage = main.StoryboardStorage(base_dir=str(base_dir))
            sibling_path = base_dir.parent / f"{base_dir.name}-outside" / "image.png"

            for storage_key in (
                "../outside/image.png",
                str(sibling_path),
                str(Path(tmpdir).parent / "external-image.png"),
            ):
                with self.subTest(storage_key=storage_key):
                    with self.assertRaises(main.SecurityError):
                        storage._resolve_safe_path(storage_key)

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

    def test_upload_shot_image_accepts_png_jpeg_and_webp_signatures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, scene = self._create_project_and_scene()
            shot = main.create_shot(
                project["id"],
                scene["id"],
                ShotCreate(shot_type="PM"),
            )

            for image_data, expected_media_type in (
                (b"\x89PNG\r\n\x1a\ncontent", "image/png"),
                (b"\xff\xd8\xffcontent", "image/jpeg"),
                (b"RIFF\x00\x00\x00\x00WEBPcontent", "image/webp"),
            ):
                with self.subTest(expected_media_type=expected_media_type):
                    request = type(
                        "RequestStub",
                        (),
                        {"body": AsyncMock(return_value=image_data)},
                    )()
                    result = asyncio.run(
                        main.upload_shot_image(
                            project["id"],
                            shot["id"],
                            request,
                        )
                    )

                    self.assertEqual(result["status"], "ok")
                    response = main.get_shot_image(project["id"], shot["id"])
                    self.assertEqual(response.media_type, expected_media_type)

    def test_reorder_shots_requires_a_complete_unique_permutation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, scene = self._create_project_and_scene()
            first = main.create_shot(project["id"], scene["id"], ShotCreate())
            second = main.create_shot(project["id"], scene["id"], ShotCreate())

            for shot_ids in (
                [first["id"], first["id"]],
                [first["id"]],
                [first["id"], second["id"], "not-a-shot"],
            ):
                with self.subTest(shot_ids=shot_ids):
                    with self.assertRaises(HTTPException) as context:
                        main.reorder_shots(
                            project["id"],
                            scene["id"],
                            ShotReorderRequest(shot_ids=shot_ids),
                        )
                    self.assertEqual(context.exception.status_code, 400)

    def test_reorder_shots_accepts_a_complete_permutation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, scene = self._create_project_and_scene()
            first = main.create_shot(project["id"], scene["id"], ShotCreate())
            second = main.create_shot(project["id"], scene["id"], ShotCreate())

            result = main.reorder_shots(
                project["id"],
                scene["id"],
                ShotReorderRequest(shot_ids=[second["id"], first["id"]]),
            )
            self.assertEqual(result["reordered_count"], 2)


if __name__ == "__main__":
    unittest.main()