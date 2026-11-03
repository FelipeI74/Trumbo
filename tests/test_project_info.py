import asyncio
import base64
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import app.database as database
import app.main as main
from app.schemas import ProjectCreate, ProjectUpdate, UserProfileUpdate


class ProjectInfoTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        patcher = patch.object(
            database,
            "DB_PATH",
            Path(self.tmpdir.name) / "trumbo.db",
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        database.initialize()

        with database.connect() as connection:
            connection.execute("DELETE FROM projects")

        self.project = main.create_project(
            ProjectCreate(title="Proyecto de prueba")
        )

    def test_project_info_fields_are_persisted(self):
        updated = main.update_project(
            self.project["id"],
            ProjectUpdate(
                title="Título actualizado",
                author="Guionista",
                project_type="Cortometraje",
                manual_duration_seconds=3600,
            ),
        )

        self.assertEqual(updated["title"], "Título actualizado")
        self.assertEqual(updated["author"], "Guionista")
        self.assertEqual(updated["project_type"], "Cortometraje")
        self.assertEqual(updated["manual_duration_seconds"], 3600)

    def test_avatar_is_validated_and_persisted_in_user_profile(self):
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        )
        avatar = (
            "data:image/png;base64,"
            + base64.b64encode(png_bytes).decode("ascii")
        )

        updated = main.update_user_profile(
            UserProfileUpdate(avatar_base64=avatar)
        )

        self.assertEqual(updated, {"status": "ok"})
        self.assertEqual(main.get_user_profile()["avatar_base64"], avatar)

    def test_avatar_rejects_mismatched_image_data(self):
        avatar = "data:image/png;base64," + base64.b64encode(
            b"not a png"
        ).decode("ascii")

        with self.assertRaises(HTTPException) as error:
            main.update_user_profile(
                UserProfileUpdate(avatar_base64=avatar)
            )

        self.assertEqual(error.exception.status_code, 400)

    def test_series_fields_can_be_saved_and_cleared(self):
        updated = main.update_project(
            self.project["id"],
            ProjectUpdate(
                project_type="Serie",
                season=1,
                episode=2,
            ),
        )
        self.assertEqual(updated["season"], 1)
        self.assertEqual(updated["episode"], 2)

        cleared = main.update_project(
            self.project["id"],
            ProjectUpdate(
                project_type="Largometraje",
                season=None,
                episode=None,
            ),
        )
        self.assertIsNone(cleared["season"])
        self.assertIsNone(cleared["episode"])

    def test_series_pdf_uses_real_author_and_episode_tag(self):
        main.update_project(
            self.project["id"],
            ProjectUpdate(
                author="Autora real",
                project_type="Serie",
                season=1,
                episode=2,
            ),
        )
        response = main.export_project_pdf(self.project["id"])

        async def read_stream():
            return b"".join([chunk async for chunk in response.body_iterator])

        pdf_bytes = asyncio.run(read_stream())
        self.assertIn(b"Autora real", pdf_bytes)
        self.assertIn(b"T01:E02", pdf_bytes)
        self.assertIn(
            b"\\251 2026 Autora real.",
            pdf_bytes,
        )

    def test_existing_database_migrates_metadata_and_global_avatar(self):
        legacy_path = Path(self.tmpdir.name) / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        try:
            connection.execute(
                """
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    format TEXT NOT NULL DEFAULT 'feature',
                    start_date TEXT,
                    work_days TEXT DEFAULT '1,2,3,4,5',
                    day_type TEXT DEFAULT 'estandar',
                    user_avatar_base64 TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            legacy_avatar = "data:image/png;base64,legacy"
            connection.execute(
                """
                INSERT INTO projects(title, user_avatar_base64)
                VALUES (?, ?)
                """,
                ("Proyecto antiguo", legacy_avatar),
            )
            connection.commit()
        finally:
            connection.close()

        with patch.object(database, "DB_PATH", legacy_path):
            database.initialize()
            with database.connect() as connection:
                project_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(projects)"
                    ).fetchall()
                }
                project = connection.execute(
                    "SELECT * FROM projects"
                ).fetchone()
                profile = connection.execute(
                    "SELECT avatar_base64 FROM user_profile WHERE id = 1"
                ).fetchone()

        self.assertTrue(
            {
                "author",
                "project_type",
                "manual_duration_seconds",
                "season",
                "episode",
            }.issubset(project_columns)
        )
        self.assertEqual(project["project_type"], "Largometraje")
        self.assertEqual(project["manual_duration_seconds"], 0)
        self.assertIsNone(project["user_avatar_base64"])
        self.assertEqual(profile["avatar_base64"], legacy_avatar)


if __name__ == "__main__":
    unittest.main()
