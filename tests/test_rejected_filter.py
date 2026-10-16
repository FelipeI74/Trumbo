import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.database as database
import app.main as main
from app.schemas import (
    BreakdownItemCreate,
    ProjectCreate,
    SceneCreate,
)


class RejectedFilterTests(unittest.TestCase):
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
            ProjectCreate(title="Rejected filter", format="feature")
        )

        self.scene = main.create_scene(
            self.project["id"],
            SceneCreate(
                heading="INT. TEST - DIA",
                body="Accion de prueba.",
                semantic_lines=[
                    {"type": "heading", "text": "INT. TEST - DIA"},
                    {"type": "action", "text": "Accion de prueba."},
                ],
            ),
        )

        # Un prop confirmed, un prop detected, un prop rejected
        main.add_breakdown_item(
            self.scene["id"],
            BreakdownItemCreate(
                category="prop",
                name="Cuchillo confirmed",
                source="manual",
                state="confirmed",
            ),
        )
        main.add_breakdown_item(
            self.scene["id"],
            BreakdownItemCreate(
                category="prop",
                name="Cuchillo detected",
                source="analysis",
                state="detected",
            ),
        )
        main.add_breakdown_item(
            self.scene["id"],
            BreakdownItemCreate(
                category="prop",
                name="Cuchillo rejected",
                source="analysis",
                state="rejected",
            ),
        )

        # Wardrobe: uno confirmed, uno rejected
        main.add_breakdown_item(
            self.scene["id"],
            BreakdownItemCreate(
                category="wardrobe",
                name="Delantal confirmed",
                source="manual",
                state="confirmed",
            ),
        )
        main.add_breakdown_item(
            self.scene["id"],
            BreakdownItemCreate(
                category="wardrobe",
                name="Delantal rejected",
                source="analysis",
                state="rejected",
            ),
        )

        self.client = TestClient(main.app)

    # --- /resources ---

    def test_resources_excludes_rejected_items(self):
        response = self.client.get(
            f"/api/projects/{self.project['id']}/resources"
        )
        self.assertEqual(response.status_code, 200)
        names = sorted(r["name"] for r in response.json()["resources"])
        self.assertNotIn("Cuchillo rejected", names)
        self.assertNotIn("Delantal rejected", names)
        self.assertIn("Cuchillo confirmed", names)
        self.assertIn("Cuchillo detected", names)
        self.assertIn("Delantal confirmed", names)

    def test_resources_includes_confirmed_and_detected(self):
        response = self.client.get(
            f"/api/projects/{self.project['id']}/resources"
        )
        names = [r["name"] for r in response.json()["resources"]]
        self.assertEqual(len(names), 3)

    # --- CSV ---

    def test_csv_excludes_rejected_props(self):
        response = self.client.get(
            f"/api/projects/{self.project['id']}/export/csv"
        )
        self.assertEqual(response.status_code, 200)
        # El CSV tiene BOM, lo quitamos
        text = response.content.decode("utf-8-sig")
        self.assertIn("Cuchillo confirmed", text)
        self.assertIn("Cuchillo detected", text)
        self.assertNotIn("Cuchillo rejected", text)

    def test_csv_excludes_rejected_wardrobe(self):
        response = self.client.get(
            f"/api/projects/{self.project['id']}/export/csv"
        )
        text = response.content.decode("utf-8-sig")
        self.assertIn("Delantal confirmed", text)
        self.assertNotIn("Delantal rejected", text)


if __name__ == "__main__":
    unittest.main()
