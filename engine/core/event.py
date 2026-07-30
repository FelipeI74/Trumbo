"""
Trumbo Engine

Core entity: Event
"""

from dataclasses import dataclass


@dataclass
class Event:
    """
    Represents a dramatic event inside a screenplay scene.

    An event marks a meaningful change in action, information,
    intention, conflict or dramatic direction.
    """

    id: str
    scene_id: str
    order: int
    title: str
    summary: str
