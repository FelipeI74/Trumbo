"""
Trumbo Engine

Service: Scene Analyzer
"""

from core.scene import Scene


class SceneAnalyzer:
    """
    Analyze a screenplay scene without modifying it.

    Every production module should consume this service instead
    of parsing screenplay text independently.
    """

    def analyze(self, scene: Scene):
        """
        Analyze a scene.

        This is the entry point for all future scene analysis.
        """

        return {
            "scene": scene,
            "events": [],
            "blocks": [],
            "characters": [],
            "locations": [],
            "props": []
        }
