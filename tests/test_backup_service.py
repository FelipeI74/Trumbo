from datetime import datetime
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.database as database
import app.main as main
import app.services.backup_service as backup_service


class BackupServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.database_path = Path(self.tmpdir.name) / "trumbo.db"
        self.database_patcher = patch.object(
            database,
            "DB_PATH",
            self.database_path,
        )
        self.database_patcher.start()
        self.addCleanup(self.database_patcher.stop)

        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("CREATE TABLE backup_test (value TEXT)")
            connection.execute(
                "INSERT INTO backup_test(value) VALUES (?)",
                ("valid",),
            )
            connection.commit()
        finally:
            connection.close()

    def test_create_backup_generates_valid_database_file(self):
        backup = backup_service.create_backup()
        backup_path = Path(backup["path"])

        self.assertTrue(backup_path.is_file())
        connection = sqlite3.connect(backup_path)
        try:
            value = connection.execute(
                "SELECT value FROM backup_test"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(value, "valid")
        self.assertGreater(backup["size_bytes"], 0)
        self.assertEqual(
            datetime.strptime(backup["timestamp"], "%Y-%m-%d_%H%M%S")
            .strftime("%Y-%m-%d_%H%M%S"),
            backup["timestamp"],
        )

    def test_rotation_keeps_only_five_database_and_data_backups(self):
        projects_directory = (
            self.database_path.parent / "data" / "projects"
        )
        projects_directory.mkdir(parents=True)
        (projects_directory / "image.txt").write_text("image", encoding="utf-8")

        for _ in range(7):
            backup_service.create_backup()

        backup_directory = self.database_path.parent / "ADUMN_BACKUPS"
        self.assertEqual(len(list(backup_directory.glob("trumbo_*.db"))), 5)
        self.assertEqual(
            len([path for path in backup_directory.glob("data_*") if path.is_dir()]),
            5,
        )

    def test_admin_endpoint_returns_success_and_backup_summary(self):
        with TestClient(main.app) as client:
            response = client.post("/api/admin/backup")

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(Path(result["path"]).is_file())
        self.assertIn("size_bytes", result)
        self.assertIn("timestamp", result)

    def test_startup_skips_backup_before_first_database_creation(self):
        self.database_path.unlink()

        with patch.object(main, "create_backup") as create_backup:
            main.startup()

        create_backup.assert_not_called()
        self.assertTrue(self.database_path.is_file())


if __name__ == "__main__":
    unittest.main()
