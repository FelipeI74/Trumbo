import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.database as database
import app.main as main
from app.schemas import ProjectCreate


class CharacterAliasEndpointsTests(unittest.TestCase):
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
            ProjectCreate(title="Alias endpoints", format="feature")
        )
        self.client = TestClient(main.app)

    def _get(self, project_id=None):
        pid = project_id if project_id is not None else self.project["id"]
        return self.client.get(f"/api/projects/{pid}/character-aliases")

    def _put(self, aliases, project_id=None):
        pid = project_id if project_id is not None else self.project["id"]
        return self.client.put(
            f"/api/projects/{pid}/character-aliases",
            json={"aliases": aliases},
        )

    # --- GET ---

    def test_get_returns_empty_list_when_no_aliases(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["project_id"], self.project["id"])
        self.assertEqual(data["aliases"], [])

    def test_get_returns_404_for_unknown_project(self):
        response = self._get(project_id=999999)
        self.assertEqual(response.status_code, 404)

    # --- PUT happy path ---

    def test_put_saves_single_alias(self):
        response = self._put([
            {"primary_name": "FELIPE AMADO", "alias_name": "DON FELIPE"},
        ])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["project_id"], self.project["id"])
        self.assertEqual(len(data["aliases"]), 1)
        self.assertEqual(data["aliases"][0]["primary_name"], "FELIPE AMADO")
        self.assertEqual(data["aliases"][0]["alias_name"], "DON FELIPE")

    def test_put_with_empty_list_clears_aliases(self):
        # Primero guardar dos
        self._put([
            {"primary_name": "FELIPE AMADO", "alias_name": "DON FELIPE"},
            {"primary_name": "FELIPE AMADO", "alias_name": "PIPE"},
        ])
        # Despues borrar todos
        response = self._put([])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["aliases"], [])

    def test_put_replaces_existing_aliases(self):
        self._put([
            {"primary_name": "FELIPE AMADO", "alias_name": "DON FELIPE"},
            {"primary_name": "FELIPE AMADO", "alias_name": "PIPE"},
        ])
        # Reemplazar con una lista distinta
        response = self._put([
            {"primary_name": "MARTA", "alias_name": "MARTITA"},
        ])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["aliases"]), 1)
        self.assertEqual(data["aliases"][0]["primary_name"], "MARTA")
        self.assertEqual(data["aliases"][0]["alias_name"], "MARTITA")

    # --- PUT validaciones ---

    def test_put_with_empty_primary_name_returns_422(self):
        response = self._put([
            {"primary_name": "", "alias_name": "DON FELIPE"},
        ])
        # Pydantic valida min_length=1 y devuelve 422
        self.assertEqual(response.status_code, 422)

    def test_put_with_primary_equals_alias_returns_400(self):
        response = self._put([
            {"primary_name": "FELIPE", "alias_name": "felipe"},
        ])
        self.assertEqual(response.status_code, 400)

    def test_put_with_duplicate_aliases_returns_400(self):
        response = self._put([
            {"primary_name": "A", "alias_name": "DON FELIPE"},
            {"primary_name": "B", "alias_name": "don felipe"},
        ])
        self.assertEqual(response.status_code, 400)

    def test_put_on_unknown_project_returns_404(self):
        response = self._put(
            [{"primary_name": "FELIPE", "alias_name": "PIPE"}],
            project_id=999999,
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
