"""
Trumbo Engine

Core entity: Block
"""

from dataclasses import dataclass


@dataclass
class Block:
    """
    Represents a physical screenplay block inside a scene.

    A block can represent a heading, action, character cue,
    dialogue, parenthetical, transition or other screenplay element.
    """

    id: str
    scene_id: str
    order: int
    block_type: str
    content: str
