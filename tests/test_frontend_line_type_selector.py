import unittest
from pathlib import Path


class FrontendLineTypeSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.app_js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
        cls.styles_css = (root / "app" / "static" / "styles.css").read_text(
            encoding="utf-8"
        )
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

    def test_screenplay_css_defines_semantic_colors_and_courier_scale(self):
        for line_type in ("heading", "action", "character", "dialogue", "parenthetical", "transition"):
            self.assertIn(f".script-line.{line_type}", self.styles_css)

        for color in ("#000000", "#cc0000", "#0055cc", "#008800", "#1a1a6e", "#666666"):
            self.assertIn(color, self.styles_css)

        self.assertIn('"Courier Prime", "Courier New", Courier, monospace', self.styles_css)
        self.assertIn("font-size: 12pt", self.styles_css)


if __name__ == "__main__":
    unittest.main()
