from engine.core.scene import Scene
from engine.core.types.block_type import BlockType
from engine.services.parsers.scene_parser import SceneParser


def test_scene_parser_classifies_realistic_spanish_scene() -> None:
    scene_content = """INT. SALA DE CONTROL - DÍA

Primer plano del teléfono que está sonando.

Enrique, que ordena papeles junto al aparato, contesta.

ENRIQUE

Radio Magallanes

Al otro lado de la línea solo suena una respiración.

ENRIQUE

¿Aló?

Pasan unos segundos.

VOZ

Se les acabó la fiesta, marxistas de mierda...

Se escucha que cortan la llamada.

Enrique queda inmóvil con el aparato en la mano.

Ravest lo ve desde cierta distancia.

Entre Ravest y Enrique está el resto del equipo trabajando frenéticamente.

Ravest se acerca a Enrique.

RAVEST

¿Quién era?

ENRIQUE

Alguien que dijo que se acabó la fiesta.

Ravest le quita el auricular y cuelga.

RAVEST

Revisa los refritos de anoche.

Le da una palmada en la espalda y vuelve a su puesto.

Enrique se sacude y vuelve a lo suyo, quedando pensativo.
"""

    scene = Scene(
        id="scene-1",
        number="1",
        interior_exterior="INT",
        general_location="SALA DE CONTROL",
        specific_location=None,
        time_of_day="DÍA",
        content=scene_content,
    )

    parsed_scene = SceneParser().parse(scene)
    blocks = parsed_scene.blocks

    assert blocks[0].block_type == BlockType.HEADING

    assert any(
        block.content == "Primer plano del teléfono que está sonando."
        and block.block_type == BlockType.ACTION
        for block in blocks
    )

    assert any(
        block.content == "ENRIQUE"
        and block.block_type == BlockType.CHARACTER
        for block in blocks
    )

    assert any(
        block.content == "VOZ"
        and block.block_type == BlockType.CHARACTER
        for block in blocks
    )

    assert any(
        block.content == "RAVEST"
        and block.block_type == BlockType.CHARACTER
        for block in blocks
    )

    assert any(
        block.content == "Ravest le quita el auricular y cuelga."
        and block.block_type == BlockType.ACTION
        for block in blocks
    )

    assert any(
        block.content == "Le da una palmada en la espalda y vuelve a su puesto."
        and block.block_type == BlockType.ACTION
        for block in blocks
    )
