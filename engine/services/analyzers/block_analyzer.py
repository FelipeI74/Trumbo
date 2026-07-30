"""
Trumbo Engine

Temporary compatibility wrapper for SceneParser.
"""

from core.scene import Scene
from core.block import Block
from services.parsers.scene_parser import SceneParser


class BlockAnalyzer:
    """
    Temporary compatibility wrapper.

    New code should use SceneParser directly.
    """

    def __init__(self) -> None:
        self._parser = SceneParser()

    def analyze(self, scene: Scene) -> list[Block]:
        """
        Return only the parsed blocks.
        """

        parsed_scene = self._parser.parse(scene)

        return parsed_scene.blocks
