from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import app.database as database
import app.main as main
from app.schemas import ProjectCreate, SceneCreate
from app.services.deepseek_service import (
    DeepSeekServiceError,
    analyze_scene_with_deepseek,
)


class DeepSeekAnalysisUnitTests(unittest.TestCase):
    def test_missing_api_key_raises_error(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
            with self.assertRaises(DeepSeekServiceError) as ctx:
                analyze_scene_with_deepseek("INT. TEST - DIA", "JUAN camina.")
            self.assertIn("DEEPSEEK_API_KEY", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_successful_analysis_with_object_elements(self, mock_urlopen):
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "elements": [
                                {"category": "character", "name": "JUAN"},
                                {"category": "prop", "name": "Vaso"},
                                {"category": "invalid_cat", "name": "Ignorado"},
                            ]
                        })
                    }
                }
            ]
        }
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = io.BytesIO(json.dumps(fake_response).encode("utf-8"))
        mock_urlopen.return_value = mock_cm

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test_key"}):
            results = analyze_scene_with_deepseek("INT. CASA - NOCHE", "JUAN toma un Vaso.")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], {"category": "character", "name": "JUAN"})
        self.assertEqual(results[1], {"category": "prop", "name": "Vaso"})

    @patch("urllib.request.urlopen")
    def test_successful_analysis_with_raw_list(self, mock_urlopen):
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps([
                            {"category": "character", "name": "MARIA"},
                            {"category": "vehicle", "name": "Taxi"},
                        ])
                    }
                }
            ]
        }
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = io.BytesIO(json.dumps(fake_response).encode("utf-8"))
        mock_urlopen.return_value = mock_cm

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test_key"}):
            results = analyze_scene_with_deepseek("EXT. CALLE - DIA", "MARIA sube a un Taxi.")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], {"category": "character", "name": "MARIA"})
        self.assertEqual(results[1], {"category": "vehicle", "name": "Taxi"})


class DeepSeekAnalysisEndpointTests(unittest.TestCase):
    def _prepare_empty_database(self, tmpdir: str) -> None:
        db_path = Path(tmpdir) / "trumbo.db"
        patcher = patch.object(database, "DB_PATH", db_path)
        patcher.start()
        self.addCleanup(patcher.stop)

        database.initialize()
        with database.connect() as connection:
            connection.execute("DELETE FROM breakdown_items")
            connection.execute("DELETE FROM scenes")
            connection.execute("DELETE FROM projects")

    @patch("app.main.analyze_scene_with_deepseek")
    def test_endpoint_delegates_to_deepseek_when_configured(self, mock_deepseek):
        mock_deepseek.return_value = [
            {"category": "character", "name": "PEDRO"},
            {"category": "prop", "name": "Maletín"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project = main.create_project(ProjectCreate(title="Test DeepSeek", format="feature"))
            scene = main.create_scene(project["id"], SceneCreate(heading="INT. SALA - DIA", body="PEDRO abre un maletín."))

            with patch.dict("os.environ", {"AI_PROVIDER": "deepseek"}):
                client = TestClient(main.app)
                response = client.post(f"/api/scenes/{scene['id']}/gemini-analysis")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["scene_id"], scene["id"])
            self.assertEqual(len(data["suggestions"]), 2)
            mock_deepseek.assert_called_once_with(
                heading="INT. SALA - DIA",
                body="PEDRO abre un maletín.",
                known_elements=[],
            )

    @patch("app.main.analyze_scene_with_deepseek")
    def test_deepseek_service_error_returns_502(self, mock_deepseek):
        mock_deepseek.side_effect = DeepSeekServiceError("Cuota de DeepSeek excedida.")

        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project = main.create_project(ProjectCreate(title="Test DeepSeek Error", format="feature"))
            scene = main.create_scene(project["id"], SceneCreate(heading="INT. SALA - DIA", body=""))

            with patch.dict("os.environ", {"AI_PROVIDER": "deepseek"}):
                client = TestClient(main.app)
                response = client.post(f"/api/scenes/{scene['id']}/gemini-analysis")

            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.json()["detail"], "Cuota de DeepSeek excedida.")


if __name__ == "__main__":
    unittest.main()

