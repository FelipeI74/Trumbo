from dataclasses import dataclass, field

from engine.core.block import Block
from engine.core.event import Event
from engine.core.character import Character
from engine.core.location import Location


@dataclass
class SceneAnalysis:
    """
    Result of analyzing a screenplay scene.
    """

    blocks: list[Block] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    characters: list[Character] = field(default_factory=list)
    locations: list[Location] = field(default_factory=list)
    props: list[str] = field(default_factory=list)
