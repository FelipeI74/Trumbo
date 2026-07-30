"""
Trumbo Engine

Core entity: Scene
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Scene:
    """
    Represents a screenplay scene.

    This is the fundamental unit of the Trumbo Engine.
    Every analysis, production task and AI process starts from a Scene.
    """

    id: str
    number: str
    interior_exterior: str
    general_location: str
    specific_location: Optional[str]
    time_of_day: str
    heading: str
    content: str
