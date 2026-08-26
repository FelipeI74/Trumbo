import re
import unittest
from pathlib import Path


class FrontendLoadProjectSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_js_path = (
            Path(__file__).resolve().parents[1] / "app" / "static" / "app.js"
        )
        cls.source = cls.app_js_path.read_text(encoding="utf-8")
        cls.index_html = (
            Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
        ).read_text(encoding="utf-8")

    def _load_project_body(self) -> str:
        marker = "async function loadProject("
        start = self.source.find(marker)
        self.assertNotEqual(start, -1, "No se encontró loadProject en app.js")

        tail = self.source[start:]
        next_marker = tail.find("function setSaveState(")
        self.assertNotEqual(next_marker, -1, "No se pudo delimitar el final de loadProject")

        return tail[:next_marker]

    def test_a_lectura_documental_valida_usa_derived_scenes(self):
        body = self._load_project_body()

        self.assertIn("/api/projects/${projectId}/document", body)
        self.assertIn("documentResponse.derived_scenes", body)
        self.assertIn("state.scenes =", body)
        self.assertIn("derivedScenes", body)

    def test_b_estado_documental_se_puebla_en_lectura_valida(self):
        self.assertIn("document: null", self.source)
        self.assertIn("documentLines: []", self.source)

        body = self._load_project_body()
        self.assertIn("state.document =", body)
        self.assertIn("documentResponse.document", body)
        self.assertIn("state.documentLines =", body)
        self.assertIn("documentResponse.lines || []", body)

    def test_c_fallback_por_404_carga_legacy_y_limpia_estado_documental(self):
        body = self._load_project_body()

        self.assertIn("response.status === 404", body)
        self.assertIn("await request(", body)
        self.assertIn("`/api/projects/${projectId}`", body)
        self.assertIn("state.scenes =", body)
        self.assertIn("legacy.scenes || []", body)
        self.assertIn("state.document = null", body)
        self.assertIn("state.documentLines = []", body)

    def test_d_fallback_por_structural_conflict(self):
        body = self._load_project_body()
        self.assertRegex(body, r"structural_conflict\s*===\s*true")
        self.assertIn("mustUseLegacy = true", body)

    def test_e_fallback_por_id_nulo(self):
        body = self._load_project_body()
        self.assertRegex(body, r"scene\?\.id\s*==\s*null")
        self.assertIn("mustUseLegacy = true", body)

    def test_f_regresion_collapse_flujo_posterior_se_mantiene(self):
        body = self._load_project_body()

        scene_list_idx = body.find("renderSceneList();")
        screenplay_idx = body.find("renderScreenplay();")
        collapse_idx = body.find("await collapseLeadingHeadinglessScene();")
        runtime_idx = body.find("await updateProjectRuntime();")

        self.assertGreaterEqual(scene_list_idx, 0)
        self.assertGreaterEqual(screenplay_idx, 0)
        self.assertGreaterEqual(collapse_idx, 0)
        self.assertGreaterEqual(runtime_idx, 0)

        self.assertLess(scene_list_idx, screenplay_idx)
        self.assertLess(screenplay_idx, collapse_idx)
        self.assertLess(collapse_idx, runtime_idx)

        self.assertNotIn("reconcileScenesFromDocument()", body)

    def test_g_rutas_de_escritura_scene_permancen_intactas(self):
        body = self._load_project_body()

        self.assertNotIn("/api/scenes/${sceneId}", body)
        self.assertNotIn("/api/projects/${state.project.id}/scenes", body)

        self.assertIn("`/api/scenes/${sceneId}`", self.source)
        self.assertIn("`/api/projects/${state.project.id}/scenes`", self.source)
        self.assertIn('method: "PATCH"', self.source)
        self.assertIn('method: "POST"', self.source)
        self.assertIn('method: "DELETE"', self.source)

    def test_active_scene_id_se_mantiene_igual(self):
        body = self._load_project_body()
        self.assertRegex(
            body,
            r"state\.activeSceneId\s*=\s*\n\s*state\.scenes\[0\]\?\.id\s*\?\?\s*\n\s*null",
        )

    def test_plan_de_rodaje_carga_y_renderiza_schedule_preview(self):
        self.assertIn("id=\"scheduleView\"", self.index_html)
        self.assertIn("id=\"generateScheduleButton\"", self.index_html)
        self.assertNotIn("scheduleMetadata", self.index_html)
        self.assertIn("ESC.", self.index_html)
        self.assertIn("LOCACIÓN", self.index_html)
        self.assertIn("SUBLOCACIÓN", self.index_html)
        self.assertIn("INT/EXT", self.index_html)
        self.assertIn("LUZ", self.index_html)
        self.assertIn("DURACIÓN", self.index_html)
        self.assertIn("ELENCO", self.index_html)
        self.assertIn("/api/projects/${state.project.id}/schedule-preview", self.source)
        self.assertIn("function renderSchedule(schedule, schedulingInput)", self.source)
        self.assertIn("function loadSchedulePreview()", self.source)
        self.assertIn("setMainView(tab.dataset.view)", self.source)
        self.assertIn("FIN JORNADA", self.source)
        self.assertIn("schedule-scene-cast", self.source)
        self.assertIn("schedule-scene-time", self.source)
        self.assertIn("schedule-scene-sublocation", self.source)
        self.assertIn("scene.sublocation", self.source)
        self.assertIn("Duración guion", self.source)

    def test_plan_de_rodaje_oculta_inspector_y_lo_restaura_en_guion(self):
        start = self.source.find("function setMainView(view) {")
        self.assertNotEqual(start, -1, "No se encontró setMainView en app.js")

        end = self.source.find("\n}", start)
        self.assertNotEqual(end, -1, "No se pudo delimitar setMainView")

        body = self.source[start:end]

        self.assertIn('$(".inspector").hidden = view === "plan-rodaje";', body)
        self.assertIn('$(".editor-toolbar").hidden = view === "plan-rodaje";', self.source)

    def test_carga_de_proyecto_reaplica_la_vista_principal_activa(self):
        body = self._load_project_body()

        self.assertIn("setMainView(state.activeMainView);", body)
        self.assertNotIn('$("#screenplayViewport")', body)
        self.assertNotIn('$("#scheduleView")', body)

    def test_sidebar_escenas_no_muestra_guion_en_plan_de_rodaje(self):
        start = self.source.find('if (view === "scenes")')
        self.assertNotEqual(start, -1, "No se encontró el handler de Escenas")

        body = self.source[start:]
        end = body.find("      }\n    );")
        self.assertNotEqual(end, -1, "No se pudo delimitar el handler de sidebar")
        body = body[:end]

        self.assertIn('if (state.activeMainView === "guion")', body)
        self.assertIn('$("#screenplayViewport").hidden = false;', body)
        self.assertNotIn(
            '$("#screenplayViewport").hidden = false;\n          renderSceneList();',
            body,
        )


if __name__ == "__main__":
    unittest.main()
