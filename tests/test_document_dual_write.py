import copy
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import app.database as database
import app.main as main
from app.document_projection import audit_scene_parity, derive_scenes_from_document_lines
from app.schemas import ProjectCreate, SceneCreate, SceneUpdate


class DocumentDualWriteTests(unittest.TestCase):
    def _prepare_empty_database(self, tmpdir: str) -> None:
        db_path = Path(tmpdir) / "trumbo.db"

        patcher = patch.object(database, "DB_PATH", db_path)
        patcher.start()
        self.addCleanup(patcher.stop)

        database.initialize()

        with database.connect() as connection:
            connection.execute("DELETE FROM document_lines")
            connection.execute("DELETE FROM documents")
            connection.execute("DELETE FROM breakdown_items")
            connection.execute("DELETE FROM notes")
            connection.execute("DELETE FROM revisions")
            connection.execute("DELETE FROM scenes")
            connection.execute("DELETE FROM projects")

    def _document_lines(self, project_id: int) -> list[dict]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    l.uuid,
                    l.document_id,
                    l.position,
                    l.type,
                    l.text,
                    l.source_scene_id,
                    l.source_line_index
                FROM document_lines l
                JOIN documents d ON d.id = l.document_id
                WHERE d.project_id = ?
                ORDER BY l.position
                """,
                (project_id,),
            ).fetchall()

        return [dict(row) for row in rows]

    def _assert_project_parity(self, project_id: int) -> None:
        payload = main.get_project(project_id)
        rebuilt = derive_scenes_from_document_lines(self._document_lines(project_id))
        parity = audit_scene_parity(payload["scenes"], rebuilt["scenes"])
        self.assertTrue(parity.ok, msg=" | ".join(parity.errors))

    def test_1_create_scene_syncs_document(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(ProjectCreate(title="DW Create", format="feature"))

            main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. CASA - DIA",
                    body="Accion de prueba",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. CASA - DIA"},
                        {"type": "action", "text": "Accion de prueba"},
                    ],
                ),
            )

            lines = self._document_lines(project["id"])
            self.assertEqual(len(lines), 2)
            self.assertEqual([line["position"] for line in lines], [0, 1])
            self._assert_project_parity(project["id"])

    def test_2_update_text_keeps_uuid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(ProjectCreate(title="DW Update Text", format="feature"))
            scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. TALLER - DIA",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. TALLER - DIA"},
                        {"type": "action", "text": "MARTA limpia la mesa."},
                    ],
                ),
            )

            before = self._document_lines(project["id"])
            target_uuid = before[1]["uuid"]

            semantic_lines = copy.deepcopy(scene["semantic_lines"])
            semantic_lines[1]["text"] = "MARTA limpia la mesa y guarda herramientas."

            main.update_scene(
                scene["id"],
                SceneUpdate(
                    body="MARTA limpia la mesa y guarda herramientas.",
                    semantic_lines=semantic_lines,
                ),
            )

            after = self._document_lines(project["id"])
            self.assertEqual(after[1]["uuid"], target_uuid)
            self.assertEqual(after[1]["text"], "MARTA limpia la mesa y guarda herramientas.")
            self._assert_project_parity(project["id"])

    def test_3_update_type_keeps_uuid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(ProjectCreate(title="DW Update Type", format="feature"))
            scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. COCINA - NOCHE",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. COCINA - NOCHE"},
                        {"type": "action", "text": "PEDRO"},
                    ],
                ),
            )

            before = self._document_lines(project["id"])
            target_uuid = before[1]["uuid"]

            semantic_lines = copy.deepcopy(scene["semantic_lines"])
            semantic_lines[1]["type"] = "character"

            main.update_scene(
                scene["id"],
                SceneUpdate(
                    semantic_lines=semantic_lines,
                ),
            )

            after = self._document_lines(project["id"])
            self.assertEqual(after[1]["uuid"], target_uuid)
            self.assertEqual(after[1]["type"], "character")
            self._assert_project_parity(project["id"])

    def test_4_update_heading_keeps_heading_uuid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(ProjectCreate(title="DW Update Heading", format="feature"))
            scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. CASA - DIA",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. CASA - DIA"},
                        {"type": "action", "text": "MARTA entra."},
                    ],
                ),
            )

            before = self._document_lines(project["id"])
            heading_uuid = before[0]["uuid"]

            semantic_lines = copy.deepcopy(scene["semantic_lines"])
            semantic_lines[0]["text"] = "INT. CASA DE PEDRO - NOCHE"

            main.update_scene(
                scene["id"],
                SceneUpdate(
                    heading="INT. CASA DE PEDRO - NOCHE",
                    semantic_lines=semantic_lines,
                ),
            )

            after = self._document_lines(project["id"])
            self.assertEqual(after[0]["uuid"], heading_uuid)
            self.assertEqual(after[0]["text"], "INT. CASA DE PEDRO - NOCHE")
            self._assert_project_parity(project["id"])

    def test_5_6_delete_and_renumber_keep_survivor_uuids_and_positions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(ProjectCreate(title="DW Delete", format="feature"))

            first = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. A - DIA",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. A - DIA"},
                        {"type": "action", "text": "A1"},
                    ],
                ),
            )
            second = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. B - DIA",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. B - DIA"},
                        {"type": "action", "text": "B1"},
                    ],
                ),
            )
            third = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. C - DIA",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. C - DIA"},
                        {"type": "action", "text": "C1"},
                    ],
                ),
            )

            before = self._document_lines(project["id"])
            survivor_map = {
                (line["source_scene_id"], line["source_line_index"]): line["uuid"]
                for line in before
                if line["source_scene_id"] in {first["id"], third["id"]}
            }

            main.delete_scene(second["id"])

            after = self._document_lines(project["id"])
            self.assertEqual([line["position"] for line in after], list(range(len(after))))

            for line in after:
                key = (line["source_scene_id"], line["source_line_index"])
                if key in survivor_map:
                    self.assertEqual(line["uuid"], survivor_map[key])

            payload = main.get_project(project["id"])
            self.assertEqual([scene["scene_number"] for scene in payload["scenes"]], [1, 2])
            self._assert_project_parity(project["id"])

    def test_7_atomicity_rollback_if_document_persist_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(ProjectCreate(title="DW Atomic", format="feature"))
            scene = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. FALLA - DIA",
                    body="Texto original",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. FALLA - DIA"},
                        {"type": "action", "text": "Texto original"},
                    ],
                ),
            )

            with self.assertRaises(RuntimeError):
                with patch("app.main.sync_project_document_from_scenes", side_effect=RuntimeError("Fallo forzado")):
                    main.update_scene(
                        scene["id"],
                        SceneUpdate(
                            body="Texto nuevo",
                            semantic_lines=[
                                {"type": "heading", "text": "INT. FALLA - DIA"},
                                {"type": "action", "text": "Texto nuevo"},
                            ],
                        ),
                    )

            payload = main.get_project(project["id"])
            self.assertEqual(payload["scenes"][0]["body"], "Texto original")
            self.assertEqual(payload["scenes"][0]["semantic_lines"][1]["text"], "Texto original")
            self._assert_project_parity(project["id"])

    def test_8_parity_after_create_update_delete_sequence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            project = main.create_project(ProjectCreate(title="DW Parity", format="feature"))

            first = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="INT. UNO - DIA",
                    semantic_lines=[
                        {"type": "heading", "text": "INT. UNO - DIA"},
                        {"type": "action", "text": "Accion 1"},
                    ],
                ),
            )
            second = main.create_scene(
                project["id"],
                SceneCreate(
                    heading="EXT. DOS - NOCHE",
                    semantic_lines=[
                        {"type": "heading", "text": "EXT. DOS - NOCHE"},
                        {"type": "dialogue", "text": "Texto 2"},
                    ],
                ),
            )

            self._assert_project_parity(project["id"])

            main.update_scene(
                first["id"],
                SceneUpdate(
                    semantic_lines=[
                        {"type": "heading", "text": "INT. UNO - DIA"},
                        {"type": "dialogue", "text": "Accion 1 convertida"},
                    ]
                ),
            )

            self._assert_project_parity(project["id"])

            main.delete_scene(second["id"])

            self._assert_project_parity(project["id"])

    def test_9_rebuild_benchmark_smoke(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_empty_database(tmpdir)

            results: dict[int, float] = {}

            for size in (50, 200, 500):
                project = main.create_project(
                    ProjectCreate(title=f"Benchmark {size}", format="feature")
                )

                for index in range(size):
                    main.create_scene(
                        project["id"],
                        SceneCreate(
                            heading=f"INT. LOCACION {index} - DIA",
                            semantic_lines=[
                                {"type": "heading", "text": f"INT. LOCACION {index} - DIA"},
                                {"type": "action", "text": "Accion de prueba"},
                            ],
                        ),
                    )

                start = time.perf_counter()
                lines = self._document_lines(project["id"])
                rebuilt = derive_scenes_from_document_lines(lines)
                duration = time.perf_counter() - start
                results[size] = duration

                parity = audit_scene_parity(main.get_project(project["id"])["scenes"], rebuilt["scenes"])
                self.assertTrue(parity.ok, msg=" | ".join(parity.errors))

            self.assertEqual(sorted(results.keys()), [50, 200, 500])


if __name__ == "__main__":
    unittest.main()
