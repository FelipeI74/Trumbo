"""
Trumbo Engine

Core entity: Character
"""

from dataclasses import dataclass


@dataclass
class Character:
    """
    Represents a screenplay character.
    """

    id: str
    name: str
