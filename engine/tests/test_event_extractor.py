from core.block import Block
from core.types.block_type import BlockType
from services.analyzers.event_extractor import (
    EventExtractor,
)


def test_event_extractor_creates_event_from_action() -> None:
    block = Block(
        id="block-1",
        scene_id="scene-1",
        order=1,
        block_type=BlockType.ACTION,
        content="Ravest abre la puerta.",
    )

    extractor = EventExtractor()

    events = extractor.extract([block])

    assert len(events) == 1

    event = events[0]

    assert event.scene_id == "scene-1"
    assert event.order == 1
    assert event.title == "Ravest abre la puerta"
    assert event.summary == "Ravest abre la puerta."
    assert event.subject == "Ravest"
    assert event.verb == "abre"
    assert event.object == "la puerta"