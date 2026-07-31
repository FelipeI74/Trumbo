"""
Trumbo Engine

Model: Character Statistics
"""

from dataclasses import dataclass

from core.character import Character


@dataclass
class CharacterStatistics:
    """
    Represents the participation of a character
    within the analyzed screenplay events.
    """

    character: Character
    first_scene_id: str
    event_count: int = 0