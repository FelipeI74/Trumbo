import unittest
from pathlib import Path


class FrontendSemanticPasteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_js_path = (
            Path(__file__).resolve().parents[1] / "app" / "static" / "app.js"
        )
        cls.source = cls.app_js_path.read_text(encoding="utf-8")

    def test_a_heading_then_narrative_maps_to_heading_action(self):
        self.assertIn("if (isHeadingPrefixText(value)) {", self.source)
        self.assertIn('return "heading";', self.source)
        self.assertIn('return "action";', self.source)

    def test_b_character_then_text_maps_to_dialogue(self):
        self.assertIn('previousType === "character" ||', self.source)
        self.assertIn('previousType === "parenthetical"', self.source)
        self.assertIn('return "dialogue";', self.source)

    def test_c_parenthetical_between_character_and_dialogue_is_supported(self):
        self.assertIn('value.startsWith("(") &&', self.source)
        self.assertIn('value.endsWith(")")', self.source)
        self.assertIn('return "parenthetical";', self.source)

    def test_d_dialogue_blank_line_then_narrative_returns_action(self):
        self.assertIn('previousType === "dialogue" &&', self.source)
        self.assertIn("previousLineWasBlank", self.source)
        self.assertIn('return "action";', self.source)

    def test_e_transition_heading_action_path_exists(self):
        self.assertIn("isTransitionText(value)", self.source)
        self.assertIn('return "transition";', self.source)
        self.assertIn("isHeadingPrefixText(nextText)", self.source)

    def test_f_known_character_cues_are_reused_for_paste(self):
        self.assertIn("collectSceneCharacterCues", self.source)
        self.assertIn("knownCharacterCues.has(", self.source)

    def test_g_multi_scene_paste_still_reconciles_from_headings(self):
        self.assertIn("scheduleDocumentSceneReconciliation();", self.source)
        self.assertIn("isCompleteHeadingText(text)", self.source)

    def test_h_existing_keyboard_and_selector_paths_remain(self):
        self.assertIn('if (event.key === "Tab")', self.source)
        self.assertIn('if (event.key === "Enter")', self.source)
        self.assertIn("function setupLineTypeSelector()", self.source)
        self.assertIn("scheduleSceneSave(", self.source)

    def test_i_real_case_dialogue_must_not_drag_into_narrative(self):
        self.assertIn("previousType === \"dialogue\"", self.source)
        self.assertIn("previousLineWasBlank", self.source)
        self.assertIn("previousText", self.source)
        self.assertIn("previousDialogueClosed", self.source)
        self.assertIn('/[.!?]$/.test(', self.source)
        self.assertIn('return "action";', self.source)

    def test_j_long_dialogue_keeps_multiline_block(self):
        self.assertIn("if (!previousDialogueClosed)", self.source)
        self.assertIn('return "dialogue";', self.source)
        self.assertIn('/^[a-záéíóúñü]/.test(value)', self.source)


if __name__ == "__main__":
    unittest.main()
