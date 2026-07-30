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
