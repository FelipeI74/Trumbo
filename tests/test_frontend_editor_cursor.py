import re
from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "app.js"


def _function_body(source: str, declaration: str, next_declaration: str) -> str:
    start = source.index(declaration)
    end = source.index(next_declaration, start)
    return source[start:end]


def test_line_input_preserves_cursor_when_text_normalization_changes_text():
    source = APP_JS.read_text(encoding="utf-8")
    helper = _function_body(
        source,
        "function setLineTextPreservingCaret(",
        "\nfunction applyLineSuggestion(",
    )
    input_handler = _function_body(
        source,
        "function handleLineInput(",
        "\nfunction handleLinePaste(",
    )

    assert "getCaretOffsetWithin(line)" in helper
    assert "line.firstChild.data = text" in helper
    assert "range.setStart(" in helper
    assert "selection.removeAllRanges()" in helper
    assert "selection.addRange(range)" in helper
    assert "setLineTextPreservingCaret(line, uppercaseText)" in input_handler
    assert "autocapitalizeLineStart(line)" in input_handler


def test_backspace_delete_does_not_reload_or_rebuild_screenplay():
    source = APP_JS.read_text(encoding="utf-8")
    keydown_handler = _function_body(
        source,
        "function handleLineKeydown(",
        "\nfunction handleLineInput(",
    )
    backspace_block = re.search(
        r'if\s*\(\s*event\.key\s*===\s*"Backspace".*?\n\s*\}\n',
        keydown_handler,
        re.DOTALL,
    )

    assert backspace_block is not None
    assert "event.preventDefault()" in backspace_block.group(0)
    assert "caretIsAtStart(line)" in backspace_block.group(0)
    assert "renderScreenplay(" not in keydown_handler
    assert "loadProject(" not in keydown_handler
    assert "reconcileScenesFromDocument(" not in keydown_handler
