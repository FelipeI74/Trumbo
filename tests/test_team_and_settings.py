import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.database as database
import app.main as main
from app.schemas import ProjectCreate


class TeamAndSettingsTests(unittest.TestCase):
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
            ProjectCreate(title="Team and settings", format="feature")
        )
        self.client = TestClient(main.app)

    def test_create_and_list_project_team_members(self):
        created = self.client.post(
            f"/api/projects/{self.project['id']}/team",
            json={
                "name": "Ana Pérez",
                "role": "Directora de fotografía",
                "email": "ana@example.com",
                "phone": "+56 9 1234 5678",
            },
        )

        self.assertEqual(created.status_code, 200)
        member = created.json()
        self.assertEqual(member["project_id"], self.project["id"])
        self.assertEqual(member["name"], "Ana Pérez")
        self.assertEqual(member["role"], "Directora de fotografía")

        listed = self.client.get(f"/api/projects/{self.project['id']}/team")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["project_id"], self.project["id"])
        self.assertEqual(listed.json()["members"], [member])

    def test_update_and_delete_project_team_member(self):
        created = self.client.post(
            f"/api/projects/{self.project['id']}/team",
            json={"name": "Ana", "role": "Producción"},
        )
        member_id = created.json()["id"]

        updated = self.client.put(
            f"/api/team/{member_id}",
            json={"phone": "555-0100"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Ana")
        self.assertEqual(updated.json()["phone"], "555-0100")

        deleted = self.client.delete(f"/api/team/{member_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"status": "deleted", "id": member_id})
        self.assertEqual(
            self.client.get(f"/api/projects/{self.project['id']}/team").json()[
                "members"
            ],
            [],
        )

    def test_team_endpoints_return_404_for_missing_records(self):
        self.assertEqual(
            self.client.get("/api/projects/999999/team").status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/projects/999999/team",
                json={"name": "Ana", "role": "Producción"},
            ).status_code,
            404,
        )
        self.assertEqual(self.client.put("/api/team/999999", json={}).status_code, 404)
        self.assertEqual(self.client.delete("/api/team/999999").status_code, 404)

    def test_settings_are_saved_and_api_key_is_masked_in_get(self):
        initial = self.client.get("/api/settings")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json(), {"ai_provider": "gemini", "api_key": ""})

        saved = self.client.put(
            "/api/settings",
            json={"ai_provider": "openrouter", "api_key": "test-secret-key"},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json(), {"status": "ok"})

        loaded = self.client.get("/api/settings")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(
            loaded.json(),
            {"ai_provider": "openrouter", "api_key": "***"},
        )
        self.assertNotIn("test-secret-key", loaded.text)

        with database.connect() as connection:
            stored_key = connection.execute(
                "SELECT value FROM app_settings WHERE key = 'api_key'"
            ).fetchone()["value"]
        self.assertEqual(stored_key, "test-secret-key")

    def test_settings_can_be_updated_independently_and_api_key_cleared(self):
        self.client.put(
            "/api/settings",
            json={"ai_provider": "deepseek", "api_key": "test-secret-key"},
        )
        self.client.put("/api/settings", json={"api_key": ""})

        self.assertEqual(
            self.client.get("/api/settings").json(),
            {"ai_provider": "deepseek", "api_key": ""},
        )


if __name__ == "__main__":
    unittest.main()
