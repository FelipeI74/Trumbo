import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.database as database
import app.main as main
from app.schemas import ProjectCreate


class ShootRateValidationTests(unittest.TestCase):
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
            ProjectCreate(title="Shoot rate validation", format="feature")
        )
        self.client = TestClient(main.app)

    def _get(self, shoot_rate):
        return self.client.get(
            f"/api/projects/{self.project['id']}/schedule-preview",
            params={"shoot_rate_seconds": shoot_rate},
        )

    def test_zero_is_rejected(self):
        response = self._get(0)
        self.assertEqual(response.status_code, 422)

    def test_negative_is_rejected(self):
        response = self._get(-100)
        self.assertEqual(response.status_code, 422)

    def test_above_max_is_rejected(self):
        response = self._get(99999)
        self.assertEqual(response.status_code, 422)

    def test_valid_value_is_accepted(self):
        response = self._get(420)
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
