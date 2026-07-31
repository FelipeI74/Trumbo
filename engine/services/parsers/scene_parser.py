"""
Trumbo Engine

Parser responsible for converting scene text
into structured screenplay blocks.
"""

import re
from uuid import uuid4

from core.block import Block
from core.scene import Scene
from core.types.block_type import BlockType
from models.parsed_scene import ParsedScene


class SceneParser:
    """
    Convert the written content of a scene into screenplay blocks.

    The parser identifies formatting and structure.
    It does not interpret dramatic meaning.
    """

    def parse(self, scene: Scene) -> ParsedScene:
        """
        Parse the scene content and return a structured result.
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

        return ParsedScene(
            blocks=blocks,
            errors=[],
            warnings=[],
        )

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

        # Scene heading
        if upper_line.startswith(
            ("INT.", "EXT.", "INT/EXT.", "EXT/INT.")
        ):
            return BlockType.HEADING

        # Editing transitions
        if upper_line in {
            "CORTE A:",
            "FUNDIDO A:",
            "DISOLVENCIA A:",
        }:
            return BlockType.TRANSITION

        # Text over image marker
        if upper_line in {
            "SUPER:",
            "GC:",
        }:
            return BlockType.SUPER

        # Text immediately following SUPER: or GC:
        if previous_type == BlockType.SUPER:
            return BlockType.SUPER

        # Parenthetical
        if normalized.startswith("(") and normalized.endswith(")"):
            return BlockType.PARENTHETICAL

        # Character cue
        if self._looks_like_character_cue(normalized):
            return BlockType.CHARACTER

        # Dialogue
        if previous_type in {
            BlockType.CHARACTER,
            BlockType.PARENTHETICAL,
            BlockType.DIALOGUE,
        }:
            return BlockType.DIALOGUE

        # Default
        return BlockType.ACTION

    def _looks_like_character_cue(self, line: str) -> bool:
        """
        Return True when a line resembles a character cue.

        Examples:
        JUAN
        JUAN (V.O.)
        JUAN (O.S.)
        JUAN (CONT'D)
        """

        if len(line) > 50:
            return False

        if line != line.upper():
            return False

        character_pattern = (
            r"^[A-ZÁÉÍÓÚÜÑ0-9 .'\-]+"
            r"(?:\s+\((?:V\.O\.|O\.S\.|CONT'D|CONTINUED)\))?$"
        )

        return re.fullmatch(character_pattern, line) is not None