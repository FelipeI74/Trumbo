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
        cls.production_css = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "static"
            / "modules"
            / "production.css"
        ).read_text(encoding="utf-8")
        cls.production_js = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "static"
            / "modules"
            / "production.js"
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

    def test_f_collapse_solo_se_ejecuta_en_fallback_legacy(self):
        body = self._load_project_body()

        scene_list_idx = body.find("renderSceneList();")
        screenplay_idx = body.find("renderScreenplay();")
        guarded_collapse = """if (!loadedFromDocument) {
    await collapseLeadingHeadinglessScene();
  }"""
        collapse_idx = body.find(guarded_collapse)
        runtime_idx = body.find("await updateProjectRuntime();")

        self.assertGreaterEqual(scene_list_idx, 0)
        self.assertGreaterEqual(screenplay_idx, 0)
        self.assertGreaterEqual(collapse_idx, 0)
        self.assertGreaterEqual(runtime_idx, 0)

        self.assertLess(scene_list_idx, screenplay_idx)
        self.assertLess(screenplay_idx, collapse_idx)
        self.assertLess(collapse_idx, runtime_idx)

        self.assertEqual(body.count("await collapseLeadingHeadinglessScene();"), 1)
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
        self.assertIn("/schedule-preview", self.source)
        self.assertIn("function renderSchedule(schedule, schedulingInput)", self.source)
        self.assertIn("function loadSchedulePreview()", self.source)
        self.assertIn("setMainView(tab.dataset.view)", self.source)
        self.assertIn("FIN JORNADA", self.source)
        self.assertIn("schedule-scene-cast", self.source)
        self.assertIn("schedule-scene-time", self.source)
        self.assertIn("schedule-scene-sublocation", self.source)
        self.assertIn("scene.sublocation", self.source)
        self.assertIn("Duración guion", self.source)

    def test_desglose_incluye_aviso_privacidad_y_flujo_de_sugerencias_ia(self):
        self.assertIn('id="aiPrivacyModal"', self.index_html)
        self.assertIn('id="cancelAiBtn"', self.index_html)
        self.assertIn('id="acceptAiBtn"', self.index_html)

        self.assertIn('id="btnAiAnalyzeScene"', self.index_html)
        self.assertIn('id="btnAiSuggestSynopsis"', self.index_html)
        self.assertIn('id="aiInspectorSuggestionsList"', self.index_html)
        self.assertIn("function renderInspectorAiSuggestions(suggestions)", self.source)
        self.assertIn("requestAiConsent(\"analysis\", event.currentTarget)", self.source)
        self.assertIn("/api/scenes/${normalizedSceneId}/gemini-analysis", self.source)
        self.assertIn("/api/scenes/${scene.id}/synopsis-suggestion", self.source)
        self.assertIn("/api/scenes/${sceneId}/breakdown", self.source)
        self.assertIn('data-ai-inspector-action="add"', self.source)
        self.assertIn('data-ai-inspector-action="dismiss"', self.source)
        self.assertIn('alert("La IA no está disponible.")', self.source)
        self.assertIn("renderProductionBreakdown();\n    renderBreakdown(activeScene());", self.source)

    def test_informes_configuran_datos_diarios_de_hoja_de_llamado(self):
        self.assertIn('id="btnEditCallSheet"', self.index_html)
        self.assertIn('id="adCallSheetModal"', self.index_html)
        self.assertIn('id="csDayNumber"', self.index_html)
        self.assertIn('id="csWeather"', self.index_html)
        self.assertIn('id="csStartTime"', self.index_html)
        self.assertIn('id="csEndTime"', self.index_html)
        self.assertIn('id="csCatering"', self.index_html)
        self.assertIn('id="csTechNotes"', self.index_html)
        self.assertIn('id="csGeneralNotes"', self.index_html)
        self.assertIn("async function openAdCallSheetEditor()", self.source)
        self.assertIn("async function loadAdCallSheetDay()", self.source)
        self.assertIn("async function saveAdCallSheetDay()", self.source)
        self.assertIn("/api/projects/${projectId}/call-sheets/${dayNumber}", self.source)
        self.assertIn('alert("Datos guardados")', self.source)

    def test_plan_de_rodaje_permite_mover_escenas_entre_jornadas(self):
        start = self.source.find("function renderSchedule(schedule, schedulingInput) {")
        self.assertNotEqual(start, -1, "No se encontró renderSchedule en app.js")
        end = self.source.find("\nasync function loadSchedulePreview()", start)
        self.assertNotEqual(end, -1, "No se pudo delimitar renderSchedule")
        body = self.source[start:end]

        self.assertIn('closest(".schedule-day")', body)
        self.assertIn('targetCards.insertBefore(', body)
        self.assertIn("targetCards.append(draggedScene)", body)
        self.assertIn("await saveScheduleManualOrder({ alertOnError: true })", body)
        self.assertIn("readManualScheduleDays()", self.source)
        self.assertIn("`/api/projects/${projectId}/schedule-manual-order`", self.source)

    def test_stripboard_ocupa_alto_disponible_con_scroll_por_columna(self):
        self.assertIn("#stripboard-root {", self.production_css)
        self.assertIn("#stripboard-root .stripboard-container {", self.production_css)
        self.assertIn("overflow-y: hidden;", self.production_css)
        self.assertIn(".strip-day-cards {\n    min-height: 150px;", self.production_css)

    def test_stripboard_generates_printable_call_sheet_for_each_day(self):
        self.assertIn('class="btn-call-sheet"', self.production_js)
        self.assertIn("window.openCallSheet(${callSheetDayNumber})", self.production_js)
        self.assertIn("window.openCallSheet = async function(dayNumber)", self.production_js)
        self.assertIn("window.lastScheduleData", self.production_js)
        self.assertIn("/call-sheets/${encodeURIComponent(dayNumber)}", self.production_js)
        self.assertIn("csData = await response.json()", self.production_js)
        self.assertIn("${escapeHtml(csData.weather || \"Por definir\")}", self.production_js)
        self.assertIn("csData.catering_notes", self.production_js)
        self.assertIn("csData.tech_notes", self.production_js)
        self.assertIn("csData.general_notes", self.production_js)
        self.assertIn("scene.scene_cast", self.production_js)
        self.assertIn("const scenesTableRows = scenes.map(scene =>", self.production_js)
        self.assertIn("<th>Resumen</th>", self.production_js)
        self.assertIn("<th>Pág</th>", self.production_js)
        self.assertIn('scene.synopsis || "Sin sinopsis"', self.production_js)
        self.assertIn("${escapeHtml(callSheetDate)}", self.production_js)
        self.assertIn('style="border-bottom: 1px solid #ccc;"', self.production_js)
        self.assertIn("window.lastSchedulingInput = scenesData", self.production_js)
        self.assertIn("window.lastSchedulingInput?.project_start_date", self.production_js)
        self.assertIn('weekday: "long"', self.production_js)
        self.assertIn("call-sheet-modal", self.production_js)
        self.assertIn("window.print()", self.production_js)
        self.assertIn("@media print", self.production_css)
        self.assertIn(".no-print {\n        display: none !important;", self.production_css)

    def test_plan_de_rodaje_oculta_inspector_y_lo_restaura_en_guion(self):
        start = self.source.find("function setMainView(view) {")
        self.assertNotEqual(start, -1, "No se encontró setMainView en app.js")

        end = self.source.find("\n}", start)
        self.assertNotEqual(end, -1, "No se pudo delimitar setMainView")

        body = self.source[start:end]

        self.assertIn("isProductionView", body)
        self.assertIn("inspector.hidden =", body)
        self.assertIn("toolbar.hidden =", body)
        

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
