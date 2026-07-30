"""
Trumbo Engine

Core entity: Scene
"""

from dataclasses import dataclass


@dataclass
class Scene:
    """
    Represents a screenplay scene.

    This is the fundamental unit of the Trumbo Engine.
    Every analysis, production task and AI process starts from a Scene.
    """

    id: str
    number: str
    heading: str
    content: str
