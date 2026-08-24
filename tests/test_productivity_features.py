import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.database as database
import app.main as main
from app.schemas import BreakdownItemCreate, BreakdownItemUpdate, NoteCreate, ProjectCreate, SceneCreate


class ProductivityFeaturesTests(unittest.TestCase):
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

    def test_scene_spelling_review_returns_misspellings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Ortografia", format="feature")
            )

            scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. CASA - DIA",
                    body=(
                        "El comentario militar sube, avanza, parece y acomoda "
                        "la cabeza junto al volante durante segundos y asiente. "
                        "El perssonaje camina y luego saluuda."
                    ),
                ),
            )

            review = main.scene_spelling_review(scene["id"])

            self.assertEqual(review["scene_id"], scene["id"])
            self.assertGreater(review["total_words"], 0)
            self.assertTrue(
                any(
                    item["word"] in {"perssonaje", "saluuda"}
                    for item in review["misspellings"]
                )
            )
            self.assertFalse(
                {
                    "comentario",
                    "militar",
                    "sube",
                    "avanza",
                    "parece",
                    "acomoda",
                    "cabeza",
                    "volante",
                    "segundos",
                    "asiente",
                }.intersection(
                    item["word"] for item in review["misspellings"]
                )
            )

    def test_scene_spelling_review_handles_missing_suggestions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Sin sugerencias", format="feature")
            )
            scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. CASA - DIA",
                    body="Palabra dudosa.",
                ),
            )

            with patch("spellchecker.SpellChecker") as spell_checker:
                checker = spell_checker.return_value
                checker.unknown.return_value = {"palabra"}
                checker.known.return_value = set()
                checker.candidates.return_value = None
                checker.correction.return_value = None

                review = main.scene_spelling_review(scene["id"])

            self.assertEqual(review["scene_id"], scene["id"])
            self.assertEqual(review["misspellings"][0]["suggestions"], [])

    def test_scheduling_input_derives_scene_cast_from_breakdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Scene cast", format="feature")
            )
            scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. CASA - DIA",
                    body="PEDRO observa desde el pasillo.",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. CASA - DIA"},
                        {"type": "action", "text": "PEDRO observa desde el pasillo."},
                        {"type": "character", "text": "MARTA"},
                        {"type": "dialogue", "text": "Hola."},
                    ],
                ),
            )
            main.add_breakdown_item(
                scene["id"],
                BreakdownItemCreate(
                    category="cast", name="PEDRO", source="manual", state="confirmed"
                ),
            )
            main.add_breakdown_item(
                scene["id"],
                BreakdownItemCreate(
                    category="scene_cast", name=" marta ", source="manual", state="confirmed"
                ),
            )
            main.add_breakdown_item(
                scene["id"],
                BreakdownItemCreate(
                    category="prop", name="Llave", source="manual", state="confirmed"
                ),
            )

            payload = main.get_project_scheduling_input(project["id"])
            scheduled_scene = payload["scenes"][0]

            self.assertEqual(scheduled_scene["characters"], ["MARTA"])
            self.assertEqual(scheduled_scene["scene_cast"], ["MARTA", "PEDRO"])
            self.assertEqual(scheduled_scene["resources"], ["Llave"])

    def test_project_pdf_export_returns_stream(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Export PDF", format="feature")
            )

            main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. CASA - NOCHE",
                    body="Linea de prueba para exportar.",
                ),
            )

            response = main.export_project_pdf(project["id"])

            self.assertEqual(response.media_type, "application/pdf")
            self.assertIn("Content-Disposition", response.headers)

    def test_project_pdf_uses_screenplay_geometry_and_paginates_without_loss(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Guion largo", format="feature")
            )
            long_action = "Accion esperada " * 900
            main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. CASA - NOCHE",
                    body=long_action,
                    semantic_lines=[
                        {"type": "heading", "text": "INT. CASA - NOCHE"},
                        {"type": "character", "text": "MARTA"},
                        {"type": "parenthetical", "text": "(susurra)"},
                        {"type": "dialogue", "text": "No podemos quedarnos aqui."},
                        {"type": "transition", "text": "CORTE A:"},
                        {"type": "action", "text": long_action},
                    ],
                ),
            )

            response = main.export_project_pdf(project["id"])

            async def read_stream():
                return b"".join([chunk async for chunk in response.body_iterator])

            pdf_bytes = asyncio.run(read_stream())
            self.assertGreaterEqual(pdf_bytes.count(b"/Type /Page"), 2)
            self.assertIn(b"MARTA", pdf_bytes)
            self.assertIn(b"No podemos quedarnos aqui.", pdf_bytes)
            self.assertIn(b"CORTE A:", pdf_bytes)
            self.assertIn(b"Accion esperada", pdf_bytes)

    def test_breakdown_item_can_change_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Desglose", format="feature")
            )

            scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. TALLER - DIA",
                    body="Hay una bicicleta y un martillo.",
                ),
            )

            created = main.add_breakdown_item(
                scene["id"],
                BreakdownItemCreate(
                    category="prop",
                    name="Bicicleta",
                    source="manual",
                    state="detected",
                ),
            )

            updated = main.update_breakdown_item(
                created["id"],
                BreakdownItemUpdate(state="confirmed"),
            )

            self.assertEqual(updated["id"], created["id"])
            self.assertEqual(updated["state"], "confirmed")

            listed = main.list_scene_breakdown(
                scene["id"],
                category="prop",
                state="confirmed",
            )

            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["id"], created["id"])

    def test_export_csv_excludes_transitions_from_characters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Transiciones CSV", format="feature")
            )
            main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. SALA - NOCHE",
                    body="",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. SALA - NOCHE"},
                        {"type": "character", "text": "LUCIA"},
                        {"type": "dialogue", "text": "Hola."},
                        {"type": "character", "text": "CUT TO:"},
                        {"type": "character", "text": "FADE IN:"},
                        {"type": "character", "text": "FADE OUT:"},
                    ],
                ),
            )

            response = main.export_project_csv(project["id"])

            text = response.body.lstrip(b"\xef\xbb\xbf").decode("utf-8")

            self.assertIn("LUCIA", text)
            self.assertNotIn("CUT TO:", text)
            self.assertNotIn("FADE IN:", text)
            self.assertNotIn("FADE OUT:", text)

    def test_export_csv_returns_stream_with_correct_headers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Proyecto CSV", format="feature")
            )
            main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. COCINA - DIA",
                    body="Accion de prueba.",
                    synopsis="Sinopsis de prueba.",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. COCINA - DIA"},
                        {"type": "action", "text": "Accion de prueba."},
                        {"type": "character", "text": "PEDRO"},
                        {"type": "dialogue", "text": "Hola."},
                    ],
                ),
            )

            response = main.export_project_csv(project["id"])

            self.assertIn("text/csv", response.media_type)
            self.assertIn("Content-Disposition", response.headers)
            self.assertIn("_desglose.csv", response.headers["Content-Disposition"])

    def test_export_csv_content_contains_expected_columns_and_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Guion Test", format="feature")
            )
            scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="EXT. PLAZA MAYOR - NOCHE",
                    body="",
                    synopsis="Escena exterior nocturna.",
                    semantic_lines=[
                        {"type": "heading", "text": "EXT. PLAZA MAYOR - NOCHE"},
                        {"type": "action", "text": "Llueve."},
                        {"type": "character", "text": "ANA"},
                        {"type": "character", "text": "ANA (V.O.)"},
                        {"type": "dialogue", "text": "Que frio."},
                    ],
                ),
            )
            main.add_breakdown_item(
                scene["id"],
                BreakdownItemCreate(
                    category="prop", name="Paraguas", source="manual", state="confirmed"
                ),
            )
            main.add_breakdown_item(
                scene["id"],
                BreakdownItemCreate(
                    category="wardrobe", name="Abrigo", source="manual", state="confirmed"
                ),
            )
            main.add_note(scene["id"], NoteCreate(category="general", body="Nota de rodaje."))

            response = main.export_project_csv(project["id"])

            # Response.body is bytes — no async iterator needed
            csv_bytes = response.body
            # Strip UTF-8 BOM before decoding
            text = csv_bytes.lstrip(b"\xef\xbb\xbf").decode("utf-8")

            self.assertIn("EXT. PLAZA MAYOR - NOCHE", text)
            self.assertIn("EXT.", text)
            self.assertIn("PLAZA MAYOR", text)
            self.assertIn("NOCHE", text)
            self.assertIn("Escena exterior nocturna.", text)
            self.assertIn("ANA", text)
            self.assertIn("Paraguas", text)
            self.assertIn("Abrigo", text)
            self.assertIn("Nota de rodaje.", text)

    def test_export_csv_unicode_characters_decode_correctly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(
                ProjectCreate(title="Película España", format="feature")
            )
            main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. ESTACION RENCA - DIA",
                    body="El pequeño vagón avanza.",
                    synopsis="Acción en locación.",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. ESTACION RENCA - DIA"},
                        {"type": "action", "text": "El pequeño vagón avanza."},
                        {"type": "character", "text": "CÁCERES"},
                        {"type": "dialogue", "text": "¡Atención!"},
                    ],
                ),
            )

            response = main.export_project_csv(project["id"])
            csv_bytes = response.body

            # BOM must be exactly EF BB BF at position 0
            self.assertTrue(csv_bytes[:3] == b"\xef\xbb\xbf")

            # Decoding as utf-8-sig removes BOM and gives clean text
            text = csv_bytes.decode("utf-8-sig")
            self.assertIn("CÁCERES", text)
            self.assertIn("pequeño", text)
            self.assertIn("Acción en locación.", text)

    def test_parse_heading_fields_handles_common_cases(self):
        cases = [
            (
                "INT. COCINA - DÍA",
                {"int_ext": "INT.", "location": "COCINA", "sublocation": "", "time_of_day": "DÍA"},
            ),
            (
                "EXT. PLAZA - NOCHE",
                {"int_ext": "EXT.", "location": "PLAZA", "sublocation": "", "time_of_day": "NOCHE"},
            ),
            (
                "INT/EXT. PUERTA - AMANECER",
                {"int_ext": "INT/EXT.", "location": "PUERTA", "sublocation": "", "time_of_day": "AMANECER"},
            ),
            (
                "INT. CASA - SALA DE ESTAR - TARDE",
                {"int_ext": "INT.", "location": "CASA", "sublocation": "SALA DE ESTAR", "time_of_day": "TARDE"},
            ),
            (
                "Sin encabezado válido",
                {"int_ext": "", "location": "", "sublocation": "", "time_of_day": ""},
            ),
            (
                "INT. SOLA SIN GUION",
                {"int_ext": "INT.", "location": "SOLA SIN GUION", "sublocation": "", "time_of_day": ""},
            ),
            (
                "INT.ESTACION RENCA - DIA",
                {"int_ext": "INT.", "location": "ESTACION RENCA", "sublocation": "", "time_of_day": "DIA"},
            ),
            (
                "EXT.PLAZA - NOCHE",
                {"int_ext": "EXT.", "location": "PLAZA", "sublocation": "", "time_of_day": "NOCHE"},
            ),
            (
                "INT. LOCUTORIO – AMANECER",
                {"int_ext": "INT.", "location": "LOCUTORIO", "sublocation": "", "time_of_day": "AMANECER"},
            ),
            (
                "EXT. PATIO – ATARDECER",
                {"int_ext": "EXT.", "location": "PATIO", "sublocation": "", "time_of_day": "ATARDECER"},
            ),
            (
                "INT. LOCUTORIO - DIA.",
                {"int_ext": "INT.", "location": "LOCUTORIO", "sublocation": "", "time_of_day": "DIA"},
            ),
            (
                "INT. LOCUTORIO - DIA(FLASHFORWARD)",
                {"int_ext": "INT.", "location": "LOCUTORIO", "sublocation": "", "time_of_day": "DIA"},
            ),
        ]
        for heading, expected in cases:
            with self.subTest(heading=heading):
                result = main._parse_heading_fields(heading)
                self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
