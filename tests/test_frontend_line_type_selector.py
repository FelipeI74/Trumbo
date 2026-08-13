import unittest
from pathlib import Path


class FrontendLineTypeSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.app_js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
        cls.index_html = (root / "app" / "static" / "index.html").read_text(
            encoding="utf-8"
        )

    def test_feature_flag_exists_and_enabled(self):
        self.assertIn("const LINE_TYPE_SELECTOR = true;", self.app_js)

    def test_toolbar_has_line_type_selector_control(self):
        self.assertIn('id="lineTypeSelector"', self.index_html)

    def test_selector_changes_active_line_via_set_line_type_preserving_caret(self):
        self.assertIn("function setupLineTypeSelector()", self.app_js)
        self.assertIn('selector.addEventListener(\n    "change",', self.app_js)
        self.assertIn("const activeLine =\n        state.activeLine;", self.app_js)
        self.assertIn("if (!activeLine)", self.app_js)
        self.assertIn("setLineType(\n        activeLine,\n        nextType,", self.app_js)
        self.assertIn("preserveCaret: true", self.app_js)


if __name__ == "__main__":
    unittest.main()
