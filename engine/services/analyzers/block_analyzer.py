"""
Trumbo Engine

Temporary compatibility wrapper for SceneParser.
"""

from core.block import Block
from core.scene import Scene
from services.parsers.scene_parser import SceneParser


class BlockAnalyzer:
    """
    Temporary wrapper kept for compatibility.

    New code should use SceneParser directly.
    """

    def __init__(self) -> None:
        self._parser = SceneParser()

    def analyze(self, scene: Scene) -> list[Block]:
        """
        Parse the scene using SceneParser.
        """

        return self._parser.parse(scene)lpha() for character in line)
