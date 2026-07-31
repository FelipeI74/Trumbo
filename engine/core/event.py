"""
Trumbo Engine

Core entity: Event
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Event:
    """
    Represents a meaningful event inside a screenplay scene.

    An event can describe a dramatic change or a concrete action
    useful for production, continuity and storyboard.
    """

    id: str
    scene_id: str
    order: int
    title: str
    summary: str

    subject: Optional[str] = None
    verb: Optional[str] = None
    object: Optional[str] = None