from __future__ import annotations

from engine.core.scene import Scene
from engine.core.types.block_type import BlockType
from engine.services.parsers.scene_parser import SceneParser


def analyze_scene_with_engine(
    scene_id: int,
    heading: str,
    body: str,
) -> dict:
    """
    Analyze a screenplay scene using the Engine parser and return the
    frontend-compatible shape expected by the existing UI.
    """

    scene = Scene(
        id=str(scene_id),
        number="1",
        interior_exterior="INT",
        general_location="",
        specific_location=None,
        time_of_day="",
        content=f"{heading}\n{body}".strip(),
    )

    parser = SceneParser()
    parsed_scene = parser.parse(scene)

    blocks = parsed_scene.blocks

    counts = {
        "heading": 0,
        "action": 0,
        "character": 0,
        "dialogue": 0,
        "parenthetical": 0,
        "transition": 0,
    }

    characters: list[str] = []
    elements: list[dict] = []

    for block in blocks:
        block_type = block.block_type
        block_type_value = block_type.value

        if block_type_value in counts:
            counts[block_type_value] += 1

        if block_type == BlockType.CHARACTER:
            name = block.content.strip()
            if name not in characters:
                characters.append(name)

        elements.append(
            {
                "line_number": len(elements) + 1,
                "type": block_type_value,
                "text": block.content,
                "confidence": 1.0,
            }
        )

    return {
        "counts": counts,
        "characters": characters,
        "elements": elements,
    }
