from engine.core.event import Event
from engine.services.analyzers.character_extractor import CharacterExtractor


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