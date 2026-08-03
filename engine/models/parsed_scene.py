"""
Trumbo Engine

Represents the result of parsing a screenplay scene.
"""

from dataclasses import dataclass, field

from engine.core.block import Block


@dataclass
class ParsedScene:
    """
    Result produced by SceneParser.

    Contains the structural information extracted from a scene,
    along with any parsing issues detected.
    """

    blocks: list[Block] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    statistics: dict = field(default_factory=dict)
