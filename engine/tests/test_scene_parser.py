from engine.core.scene import Scene
from engine.core.types.block_type import BlockType
from engine.services.parsers.scene_parser import SceneParser


def test_scene_parser_recognizes_character_cue_extensions() -> None:
    scene = Scene(
        id="2",
        number="2",
        interior_exterior="INT",
        general_location="ESTUDIO",
        specific_location=None,
        time_of_day="DÍA",
        content="""
JUAN (V.O.)

No recuerdo cuándo empezó todo.

MARÍA (O.S.)

¿Juan?

JUAN (CONT'D)

Estoy aquí.
""",
    )

    parser = SceneParser()
    parsed_scene = parser.parse(scene)

    assert len(parsed_scene.blocks) == 6

    assert parsed_scene.blocks[0].block_type == BlockType.CHARACTER
    assert parsed_scene.blocks[0].content == "JUAN (V.O.)"

    assert parsed_scene.blocks[1].block_type == BlockType.DIALOGUE

    assert parsed_scene.blocks[2].block_type == BlockType.CHARACTER
    assert parsed_scene.blocks[2].content == "MARÍA (O.S.)"

    assert parsed_scene.blocks[3].block_type == BlockType.DIALOGUE

    assert parsed_scene.blocks[4].block_type == BlockType.CHARACTER
    assert parsed_scene.blocks[4].content == "JUAN (CONT'D)"

    assert parsed_scene.blocks[5].block_type == BlockType.DIALOGUE

def test_scene_parser_recognizes_parenthetical() -> None:
    scene = Scene(
        id="3",
        number="3",
        interior_exterior="INT",
        general_location="CASA",
        specific_location=None,
        time_of_day="NOCHE",
        content="""
JUAN

(con rabia)

No vuelvas.
""",
    )

    parser = SceneParser()
    parsed_scene = parser.parse(scene)

    assert len(parsed_scene.blocks) == 3

    assert parsed_scene.blocks[0].block_type == BlockType.CHARACTER
    assert parsed_scene.blocks[1].block_type == BlockType.PARENTHETICAL
    assert parsed_scene.blocks[2].block_type == BlockType.DIALOGUE

def test_scene_parser_recognizes_transitions() -> None:
    scene = Scene(
        id="4",
        number="4",
        interior_exterior="INT",
        general_location="CASA",
        specific_location=None,
        time_of_day="NOCHE",
        content="""
CORTE A:

FUNDIDO A:

DISOLVENCIA A:
""",
    )

    parser = SceneParser()
    parsed_scene = parser.parse(scene)

    assert len(parsed_scene.blocks) == 3

    assert parsed_scene.blocks[0].block_type == BlockType.TRANSITION
    assert parsed_scene.blocks[1].block_type == BlockType.TRANSITION
    assert parsed_scene.blocks[2].block_type == BlockType.TRANSITION
def test_scene_parser_recognizes_super_and_gc() -> None:
    scene = Scene(
        id="5",
        number="5",
        interior_exterior="EXT",
        general_location="SANTIAGO",
        specific_location=None,
        time_of_day="DÍA",
        content="""
GC:

SANTIAGO, 11 DE SEPTIEMBRE DE 1973

SUPER:

TRES HORAS DESPUÉS
""",
    )

    parser = SceneParser()
    parsed_scene = parser.parse(scene)

    assert len(parsed_scene.blocks) == 4

    assert parsed_scene.blocks[0].block_type == BlockType.SUPER
    assert parsed_scene.blocks[1].block_type == BlockType.SUPER
    assert parsed_scene.blocks[2].block_type == BlockType.SUPER
    assert parsed_scene.blocks[3].block_type == BlockType.SUPER