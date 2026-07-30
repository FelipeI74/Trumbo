"""
Trumbo Engine

Parser responsible for converting scene text
into structured screenplay blocks.
"""

from uuid import uuid4

from core.block import Block
from core.scene import Scene
from core.types.block_type import BlockType


class SceneParser:
    """
    Convert the written content of a scene into screenplay blocks.

    The parser identifies formatting and structure.
    It does not interpret dramatic meaning.
    """

    def parse(self, scene: Scene) -> list[Block]:
        """
        Parse the scene content and return its structured blocks.
        """

        blocks: list[Block] = []
        previous_type: BlockType | None = None

        lines = [
            line.strip()
            for line in scene.content.splitlines()
            if line.strip()
        ]

        for order, line in enumerate(lines, start=1):
            block_type = self._detect_block_type(
                line=line,
                previous_type=previous_type,
            )

            block = Block(
                id=str(uuid4()),
                scene_id=scene.id,
                order=order,
                block_type=block_type,
                content=line,
            )

            blocks.append(block)
            previous_type = block_type

        return blocks

    def _detect_block_type(
        self,
        line: str,
        previous_type: BlockType | None,
    ) -> BlockType:
        """
        Detect the screenplay block type using deterministic rules.
        """

        normalized = line.strip()
        upper_line = normalized.upper()

        if upper_line.startswith(
            ("INT.", "EXT.", "INT/EXT.", "EXT/INT.")
        ):
            return BlockType.HEADING

        if upper_line.endswith(
            ("A:", "CORTE A:", "FUNDIDO A:")
        ):
            return BlockType.TRANSITION

        if normalized.startswith("(") and normalized.endswith(")"):
            return BlockType.PARENTHETICAL

        if self._looks_like_character_cue(normalized):
            return BlockType.CHARACTER

        if previous_type in {
            BlockType.CHARACTER,
            BlockType.PARENTHETICAL,
            BlockType.DIALOGUE,
        }:
            return BlockType.DIALOGUE

        return BlockType.ACTION

    def _looks_like_character_cue(self, line: str) -> bool:
        """
        Return True when a line resembles a character cue.
        """

        if line != line.upper():
            return False

        if len(line) > 40:
            return False

        if line.endswith((".", ":", "!", "?")):
            return False

        return any(character.isalpha() for character in line)
