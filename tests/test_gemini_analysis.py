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
    SceneUpdate,
)
from app.services.gemini_service import GeminiServiceError
from app.services.synopsis_service import (
    SynopsisServiceError,
    suggest_scene_synopsis,
)


class GeminiAnalysisEndpointTests(unittest.TestCase):
    def _prepare_empty_database(self, tmpdir: str) -> None:
        db_path = Path(tmpdir) / "trumbo.db"

        patcher = patch.object(database, "DB_PATH", db_path)
        patcher.start()
        self.addCleanup(patcher.stop)

        env_patcher = patch.dict("os.environ", {"AI_PROVIDER": "gemini"})
        env_patcher.start()
        self.addCleanup(env_patcher.stop)

        database.initialize()

        with database.connect() as connection:
            connection.execute("DELETE FROM breakdown_items")
            connection.execute("DELETE FROM notes")
            connection.execute("DELETE FROM revisions")
            connection.execute("DELETE FROM scenes")
            connection.execute("DELETE FROM projects")

    def _create_project_and_scene(
        self,
        heading: str = "INT. COCINA - DIA",
        body: str = "JUAN toma un vaso de agua.",
    ) -> tuple[dict, dict]:
        project = main.create_project(
            ProjectCreate(title="Test Gemini Analysis", format="feature")
        )
        scene = main.create_scene(
            project["id"],
            SceneCreate(
                heading=heading,
                body=body,
            ),
        )
        return project, scene

    @patch("app.main.analyze_scene_with_gemini")
    def test_nonexistent_scene_returns_404_without_calling_gemini(
        self, mock_gemini
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            client = TestClient(main.app)

            response = client.post("/api/scenes/99999/gemini-analysis")

            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "Escena no encontrada")
            mock_gemini.assert_not_called()

    @patch("app.main.analyze_scene_with_gemini")
    def test_valid_scene_returns_suggestions_with_mocked_gemini(
        self, mock_gemini
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            _, scene = self._create_project_and_scene(
                heading="INT. OFICINA - DIA",
                body="CLARA revisa un expediente sobre el escritorio.",
            )

            mock_gemini.return_value = [
                {"category": "prop", "name": "expediente"},
                {"category": "furniture", "name": "escritorio"},
                {"category": "character", "name": "CLARA"},
            ]

            client = TestClient(main.app)
            response = client.post(f"/api/scenes/{scene['id']}/gemini-analysis")

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["scene_id"], scene["id"])
            self.assertEqual(
                data["suggestions"],
                [
                    {"category": "prop", "name": "expediente"},
                    {"category": "furniture", "name": "escritorio"},
                    {"category": "character", "name": "CLARA"},
                ],
            )
            mock_gemini.assert_called_once_with(
                heading="INT. OFICINA - DIA",
                body="CLARA revisa un expediente sobre el escritorio.",
                known_elements=[],
            )

    @patch("app.main.analyze_scene_with_gemini")
    def test_breakdown_items_immutability_and_state_preservation(
        self, mock_gemini
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            _, scene = self._create_project_and_scene()

            # Insert pre-existing breakdown items with various states
            main.add_breakdown_item(
                scene["id"],
                BreakdownItemCreate(
                    category="prop",
                    name="Cuchillo",
                    source="manual",
                    state="confirmed",
                ),
            )
            main.add_breakdown_item(
                scene["id"],
                BreakdownItemCreate(
                    category="furniture",
                    name="Mesa",
                    source="analysis",
                    state="rejected",
                ),
            )
            main.add_breakdown_item(
                scene["id"],
                BreakdownItemCreate(
                    category="wardrobe",
                    name="Delantal",
                    source="analysis",
                    state="detected",
                ),
            )

            with database.connect() as connection:
                records_before = database.rows(
                    connection,
                    """
                    SELECT id, scene_id, category, name, source, state
                    FROM breakdown_items
                    ORDER BY id
                    """,
                )

            self.assertEqual(len(records_before), 3)

            mock_gemini.return_value = [
                {"category": "prop", "name": "Cuchillo"},
                {"category": "prop", "name": "Taza nueva"},
                {"category": "furniture", "name": "Mesa"},
            ]

            client = TestClient(main.app)
            response = client.post(f"/api/scenes/{scene['id']}/gemini-analysis")
            self.assertEqual(response.status_code, 200)

            with database.connect() as connection:
                records_after = database.rows(
                    connection,
                    """
                    SELECT id, scene_id, category, name, source, state
                    FROM breakdown_items
                    ORDER BY id
                    """,
                )

            # Assert exact equality of all rows, states, and counts
            self.assertEqual(records_before, records_after)

    @patch("app.main.analyze_scene_with_gemini")
    def test_gemini_service_error_returns_502(self, mock_gemini):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            _, scene = self._create_project_and_scene()

            mock_gemini.side_effect = GeminiServiceError(
                "Cuota de Gemini excedida o límite de solicitudes alcanzado."
            )

            client = TestClient(main.app)
            response = client.post(f"/api/scenes/{scene['id']}/gemini-analysis")

            self.assertEqual(response.status_code, 502)
            self.assertEqual(
                response.json()["detail"],
                "Cuota de Gemini excedida o límite de solicitudes alcanzado.",
            )

    @patch("urllib.request.urlopen")
    @patch("app.main.analyze_scene_with_gemini")
    def test_local_operations_never_trigger_gemini(
        self, mock_gemini, mock_urlopen
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            project, scene = self._create_project_and_scene()

            client = TestClient(main.app)

            # 1. Update scene content (simulating autosave)
            main.update_scene(
                scene["id"],
                SceneUpdate(
                    body="JUAN camina hacia la puerta.",
                ),
            )

            # 2. Local engine analysis (which runs on scene switch / debounced typing)
            main.analyze_scene(scene["id"])

            # 3. Add breakdown item
            main.add_breakdown_item(
                scene["id"],
                BreakdownItemCreate(
                    category="prop",
                    name="Puerta",
                    source="manual",
                    state="confirmed",
                ),
            )

            # 4. List scene breakdown items
            client.get(f"/api/scenes/{scene['id']}/breakdown")

            # 5. Read project scenes
            client.get(f"/api/projects/{project['id']}")

            # Verify no calls to Gemini wrapper or external network
            mock_gemini.assert_not_called()
            mock_urlopen.assert_not_called()

    @patch("app.main.suggest_scene_synopsis")
    def test_synopsis_suggestion_returns_generated_synopsis(self, mock_suggest):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            _, scene = self._create_project_and_scene(
                heading="INT. OFICINA - DIA",
                body="CLARA revisa un expediente.",
            )
            mock_suggest.return_value = "CLARA descubre un expediente."

            response = TestClient(main.app).post(
                f"/api/scenes/{scene['id']}/synopsis-suggestion"
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {
                    "scene_id": scene["id"],
                    "synopsis": "CLARA descubre un expediente.",
                },
            )
            mock_suggest.assert_called_once_with(
                heading="INT. OFICINA - DIA",
                body="CLARA revisa un expediente.",
            )

    @patch("app.main.suggest_scene_synopsis")
    def test_synopsis_suggestion_returns_404_for_missing_scene(self, mock_suggest):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            response = TestClient(main.app).post(
                "/api/scenes/99999/synopsis-suggestion"
            )

            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "Escena no encontrada")
            mock_suggest.assert_not_called()

    @patch("app.main.suggest_scene_synopsis")
    def test_synopsis_service_error_returns_502(self, mock_suggest):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)
            _, scene = self._create_project_and_scene()
            mock_suggest.side_effect = SynopsisServiceError(
                "El proveedor de IA devolvió una respuesta inválida."
            )

            response = TestClient(main.app).post(
                f"/api/scenes/{scene['id']}/synopsis-suggestion"
            )

            self.assertEqual(response.status_code, 502)
            self.assertEqual(
                response.json()["detail"],
                "El proveedor de IA devolvió una respuesta inválida.",
            )

    @patch.dict(
        "os.environ",
        {"AI_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"},
    )
    @patch("app.services.synopsis_service.urllib.request.urlopen")
    def test_synopsis_service_extracts_gemini_text(self, mock_urlopen):
        response = mock_urlopen.return_value.__enter__.return_value
        response.read.return_value = (
            b'{"candidates":[{"content":{"parts":[{"text":"Sinopsis breve."}]}}]}'
        )

        synopsis = suggest_scene_synopsis(
            heading="INT. CASA - DIA",
            body="ANA entra en la habitación.",
        )

        self.assertEqual(synopsis, "Sinopsis breve.")
        request = mock_urlopen.call_args.args[0]
        self.assertIn("generateContent", request.full_url)

    @patch("app.services.synopsis_service.urllib.request.urlopen")
    def test_synopsis_service_sends_bearer_auth_for_openai_compatible_providers(
        self, mock_urlopen
    ):
        response = mock_urlopen.return_value.__enter__.return_value
        response.read.return_value = (
            b'{"choices":[{"message":{"content":"Sinopsis breve."}}]}'
        )

        for provider, api_key in (
            ("openrouter", "fake-openrouter-key"),
            ("deepseek", "fake-deepseek-key"),
        ):
            with self.subTest(provider=provider):
                mock_urlopen.reset_mock()
                with patch.dict(
                    "os.environ",
                    {
                        "AI_PROVIDER": provider,
                        "OPENROUTER_API_KEY": api_key,
                        "DEEPSEEK_API_KEY": api_key,
                    },
                ):
                    synopsis = suggest_scene_synopsis(
                        heading="INT. CASA - DIA",
                        body="ANA entra en la habitación.",
                    )

                self.assertEqual(synopsis, "Sinopsis breve.")
                request = mock_urlopen.call_args.args[0]
                self.assertEqual(
                    request.get_header("Authorization"),
                    f"Bearer {api_key}",
                )


if __name__ == "__main__":
    unittest.main()
