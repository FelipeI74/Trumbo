from engine.core.event import Event
from engine.core.block import Block
from engine.core.types.block_type import BlockType
from engine.services.analyzers.character_extractor import CharacterExtractor
from engine.services.analyzers.event_extractor import EventExtractor


def test_character_extractor_groups_events_by_character() -> None:

    events = [

        Event(
            id="1",
            scene_id="24",
            order=1,
            title="",
            summary="",
            subject="Ravest",
        ),

        Event(
            id="2",
            scene_id="24",
            order=2,
            title="",
            summary="",
            subject="Enrique",
        ),

        Event(
            id="3",
            scene_id="24",
            order=3,
            title="",
            summary="",
            subject="Ravest",
        ),
    ]

    extractor = CharacterExtractor()

    statistics = extractor.extract(events)

    assert len(statistics) == 2

    ravest = next(
        item
        for item in statistics
        if item.character.name == "Ravest"
    )

    enrique = next(
        item
        for item in statistics
        if item.character.name == "Enrique"
    )

    assert ravest.event_count == 2
    assert ravest.first_scene_id == "24"

    assert enrique.event_count == 1
    assert enrique.first_scene_id == "24"


def test_character_extractor_detects_proper_name_mentioned_in_action() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="40",
            order=1,
            block_type=BlockType.ACTION,
            content="De él baja Guillermo Ravest, con un ejemplar del diario El Siglo bajo el brazo.",
        ),
    ]

    events = EventExtractor().extract(blocks)
    characters = CharacterExtractor().extract(events)

    assert any(
        item.character.name == "Guillermo Ravest"
        for item in characters
    )