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
from app.services.openrouter_service import (
    DEFAULT_OPENROUTER_MODEL,
    OpenRouterServiceError,
    analyze_scene_with_openrouter,
)


class OpenRouterAnalysisUnitTests(unittest.TestCase):
    def test_default_model_is_openrouter_free(self):
        self.assertEqual(DEFAULT_OPENROUTER_MODEL, "openrouter/free")

    def test_missing_api_key_raises_error(self):
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "", "DEEPSEEK_API_KEY": ""}):
            with self.assertRaises(OpenRouterServiceError) as ctx:
                analyze_scene_with_openrouter("INT. TEST - DIA", "JUAN camina.")
            self.assertIn("OPENROUTER_API_KEY", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_empty_content_returns_empty_list(self, mock_urlopen):
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": ""
                    }
                }
            ]
        }
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = io.BytesIO(json.dumps(fake_response).encode("utf-8"))
        mock_urlopen.return_value = mock_cm

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test_key"}):
            results = analyze_scene_with_openrouter("INT. TEST - DIA", "JUAN camina.")

        self.assertEqual(results, [])

    @patch("urllib.request.urlopen")
    def test_whitespace_content_returns_empty_list(self, mock_urlopen):
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": "   \n\t  "
                    }
                }
            ]
        }
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = io.BytesIO(json.dumps(fake_response).encode("utf-8"))
        mock_urlopen.return_value = mock_cm

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test_key"}):
            results = analyze_scene_with_openrouter("INT. TEST - DIA", "JUAN camina.")

        self.assertEqual(results, [])

    @patch("urllib.request.urlopen")
    def test_markdown_wrapped_json_parsed_properly(self, mock_urlopen):
        raw_markdown = (
            "Aquí tienes el desglose solicitado:\n"
            "```json\n"
            "[\n"
            "  {\"category\": \"stunt\", \"name\": \"Doble de acción\"},\n"
            "  {\"category\": \"prop\", \"name\": \"Mochila\"}\n"
            "]\n"
            "```\n"
            "Espero que sea de ayuda."
        )
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": raw_markdown
                    }
                }
            ]
        }
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = io.BytesIO(json.dumps(fake_response).encode("utf-8"))
        mock_urlopen.return_value = mock_cm

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test_key"}):
            results = analyze_scene_with_openrouter("INT. CASA - NOCHE", "JUAN cae.")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], {"category": "stunt", "name": "Doble de acción"})
        self.assertEqual(results[1], {"category": "prop", "name": "Mochila"})

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

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test_key"}):
            results = analyze_scene_with_openrouter("INT. CASA - NOCHE", "JUAN toma un Vaso.")

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

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test_key"}):
            results = analyze_scene_with_openrouter("EXT. CALLE - DIA", "MARIA sube a un Taxi.")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], {"category": "character", "name": "MARIA"})
        self.assertEqual(results[1], {"category": "vehicle", "name": "Taxi"})

    @patch("urllib.request.urlopen")
    def test_known_elements_injected_and_no_response_format_param(self, mock_urlopen):
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps([
                            {"category": "Stunt", "name": "Doble de acción para HOMBRE"},
                        ])
                    }
                }
            ]
        }
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = io.BytesIO(json.dumps(fake_response).encode("utf-8"))
        mock_urlopen.return_value = mock_cm

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test_key"}):
            results = analyze_scene_with_openrouter(
                "EXT. CARRETERA - NOCHE",
                "Frenazo brusco de auto.",
                known_elements=["character: CONDUCTOR", "vehicle: Auto"],
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], {"category": "stunt", "name": "Doble de acción para HOMBRE"})

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        sent_data = json.loads(req.data.decode("utf-8"))
        self.assertNotIn("response_format", sent_data)

        system_msg = sent_data["messages"][0]["content"]
        self.assertIn("character: CONDUCTOR", system_msg)
        self.assertIn("vehicle: Auto", system_msg)
        self.assertIn("Devuelve ÚNICAMENTE el array JSON", system_msg)


class OpenRouterAnalysisEndpointTests(unittest.TestCase):
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

    @patch("app.main.analyze_scene_with_openrouter")
    def test_endpoint_delegates_to_openrouter_when_configured(self, mock_openrouter):
        mock_openrouter.return_value = [
            {"category": "character", "name": "PEDRO"},
            {"category": "prop", "name": "Maletín"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project = main.create_project(ProjectCreate(title="Test OpenRouter", format="feature"))
            scene = main.create_scene(project["id"], SceneCreate(heading="INT. SALA - DIA", body="PEDRO abre un maletín."))

            with patch.dict("os.environ", {"AI_PROVIDER": "openrouter"}):
                client = TestClient(main.app)
                response = client.post(f"/api/scenes/{scene['id']}/gemini-analysis")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["scene_id"], scene["id"])
            self.assertEqual(len(data["suggestions"]), 2)
            mock_openrouter.assert_called_once_with(
                heading="INT. SALA - DIA",
                body="PEDRO abre un maletín.",
                known_elements=[],
            )

    @patch("app.main.analyze_scene_with_openrouter")
    def test_openrouter_service_error_returns_502(self, mock_openrouter):
        mock_openrouter.side_effect = OpenRouterServiceError("Cuota de OpenRouter excedida.")

        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project = main.create_project(ProjectCreate(title="Test OpenRouter Error", format="feature"))
            scene = main.create_scene(project["id"], SceneCreate(heading="INT. SALA - DIA", body=""))

            with patch.dict("os.environ", {"AI_PROVIDER": "openrouter"}):
                client = TestClient(main.app)
                response = client.post(f"/api/scenes/{scene['id']}/gemini-analysis")

            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.json()["detail"], "Cuota de OpenRouter excedida.")


if __name__ == "__main__":
    unittest.main()
