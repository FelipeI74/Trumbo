from core.scene import Scene
from core.types.block_type import BlockType
from services.parsers.scene_parser import SceneParser


def test_scene_parser_returns_expected_blocks() -> None:
    scene = Scene(
        id="1",
        number="1",
        interior_exterior="INT",
        general_location="CASA",
        specific_location="COCINA",
        time_of_day="NOCHE",
        content="""
Juan entra.

JUAN

Hola.

MARÍA

¿Qué haces aquí?
""",
    )

    parser = SceneParser()
    parsed_scene = parser.parse(scene)

    assert len(parsed_scene.blocks) == 5

    assert parsed_scene.blocks[0].block_type == BlockType.ACTION
    assert parsed_scene.blocks[1].block_type == BlockType.CHARACTER
    assert parsed_scene.blocks[2].block_type == BlockType.DIALOGUE
    assert parsed_scene.blocks[3].block_type == BlockType.CHARACTER
    assert parsed_scene.blocks[4].block_type == BlockType.DIALOGUE

    assert parsed_scene.errors == []
    assert parsed_scene.warnings == []
