import re
from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "app.js"


def test_save_scene_node_skips_when_scene_is_already_saving() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    match = re.search(
        r"async function saveSceneNode\(.*?(?=\n}\n\nfunction )",
        source,
        re.DOTALL,
    )

    assert match is not None, "No se encontró saveSceneNode en app.js"

    function_body = match.group(0)
    guard = "state.savingScenes.has(sceneId)"
    request_start = "const updated = await request("

    assert guard in function_body
    assert function_body.index(guard) < function_body.index(request_start)
