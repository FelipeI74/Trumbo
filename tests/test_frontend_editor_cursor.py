import re
from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "app.js"
INDEX_HTML = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
STYLES_CSS = Path(__file__).resolve().parents[1] / "app" / "static" / "styles.css"


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
    assert keydown_handler.index("mergeWithPreviousLine(line)") < keydown_handler.index(
        "event.preventDefault()",
        keydown_handler.index('event.key === "Backspace"'),
    )


def test_structural_reconciliation_waits_until_editor_line_blurs_and_restores_scroll():
    source = APP_JS.read_text(encoding="utf-8")
    scheduler = _function_body(
        source,
        "function scheduleDocumentSceneReconciliation(",
        "\nasync function materializeScenesFromDraftDocument(",
    )
    reconcile = _function_body(
        source,
        "async function reconcileScenesFromDocument(",
        "\nfunction editorHasFocusedLine(",
    )
    helpers = _function_body(
        source,
        "function editorHasFocusedLine(",
        "\nfunction scheduleDocumentSceneReconciliation(",
    )

    assert "editorHasFocusedLine(editor)" in scheduler
    assert "scheduleDocumentSceneReconciliation(250)" in scheduler
    assert "captureScrollPositions(editor)" in reconcile
    assert "restoreScrollPositions(scrollPositions)" in reconcile
    assert "activeElement.classList.contains(\"script-line\")" in helpers


def test_autosave_is_debounced_and_does_not_replace_editor_content():
    source = APP_JS.read_text(encoding="utf-8")
    schedule_save = _function_body(
        source,
        "function scheduleSceneSave(",
        "\nasync function saveSceneById(",
    )
    save_scene = _function_body(
        source,
        "async function saveSceneNode(",
        "\nasync function saveProductionNumber(",
    )

    assert "clearTimeout(previousTimer)" in schedule_save
    assert "}, 650);" in schedule_save
    assert "await request(" in save_scene
    assert "innerHTML" not in save_scene
    assert "replaceChildren(" not in save_scene


def test_screenplay_context_menu_is_wired_to_editor_actions():
    source = APP_JS.read_text(encoding="utf-8")
    markup = INDEX_HTML.read_text(encoding="utf-8")
    styles = STYLES_CSS.read_text(encoding="utf-8")

    assert 'id="customContextMenu"' in markup
    assert 'data-action="cut"' in markup
    assert 'data-action="copy"' in markup
    assert 'data-action="paste"' in markup
    assert 'data-action="character"' in markup
    assert 'data-action="action"' in markup
    assert 'data-action="dialogue"' in markup
    assert "setupScreenplayContextMenu();" in source
    assert 'editor.addEventListener("contextmenu"' in source
    assert 'document.execCommand("insertText", false, text)' in source
    assert 'setLineType(line, action, { preserveCaret: true })' in source
    assert ".custom-context-menu.active" in styles
