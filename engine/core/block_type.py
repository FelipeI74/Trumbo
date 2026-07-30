"""
Trumbo Engine

Enumeration: BlockType
"""

from enum import Enum


class BlockType(Enum):
    """
    Official screenplay block types supported by Trumbo.
    """

    HEADING = "heading"
    ACTION = "action"
    CHARACTER = "character"
    DIALOGUE = "dialogue"
    PARENTHETICAL = "parenthetical"
    TRANSITION = "transition"
    SHOT = "shot"
    LYRICS = "lyrics"
