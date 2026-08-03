"""
Trumbo Engine

Parser responsible for converting scene text
into structured screenplay blocks.
"""

import re
from uuid import uuid4

from engine.core.block import Block
from engine.core.scene import Scene
from engine.core.types.block_type import BlockType
from engine.models.parsed_scene import ParsedScene


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
        order = 0
        dialogue_state = "idle"
        super_state = "idle"

        for raw_line in scene.content.splitlines():
            line = raw_line.strip()

            if not line:
                if dialogue_state == "active":
                    previous_type = None
                    dialogue_state = "idle"
                    continue

                if super_state == "active":
                    previous_type = None
                    super_state = "idle"
                    continue

                if dialogue_state == "pending":
                    previous_type = None
                    continue

                if super_state == "pending":
                    previous_type = None
                    continue

                previous_type = None
                dialogue_state = "idle"
                super_state = "idle"
                continue

            order += 1

            block_type = self._detect_block_type(
                line=line,
                previous_type=previous_type,
                dialogue_state=dialogue_state,
                super_state=super_state,
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

            if block_type == BlockType.CHARACTER:
                dialogue_state = "pending"
                super_state = "idle"
            elif block_type == BlockType.PARENTHETICAL:
                dialogue_state = "pending"
                super_state = "idle"
            elif block_type == BlockType.DIALOGUE:
                dialogue_state = "active"
                super_state = "idle"
            elif block_type == BlockType.SUPER:
                if line.upper() in {"SUPER:", "GC:"}:
                    super_state = "pending"
                else:
                    super_state = "active"
                dialogue_state = "idle"
            else:
                dialogue_state = "idle"
                super_state = "idle"

        return ParsedScene(
            blocks=blocks,
            errors=[],
            warnings=[],
        )

    def _detect_block_type(
        self,
        line: str,
        previous_type: BlockType | None,
        dialogue_state: str = "idle",
        super_state: str = "idle",
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

        if upper_line in {
            "CORTE A:",
            "FUNDIDO A:",
            "DISOLVENCIA A:",
        }:
            return BlockType.TRANSITION

        if upper_line in {
            "SUPER:",
            "GC:",
        }:
            return BlockType.SUPER

        if super_state in {"pending", "active"}:
            return BlockType.SUPER

        if previous_type == BlockType.SUPER:
            return BlockType.SUPER

        if normalized.startswith("(") and normalized.endswith(")"):
            return BlockType.PARENTHETICAL

        if self._looks_like_character_cue(normalized):
            return BlockType.CHARACTER

        if dialogue_state == "pending":
            return BlockType.DIALOGUE

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

        if len(line) > 50:
            return False

        if line != line.upper():
            return False

        character_pattern = (
            r"^[A-ZÁÉÍÓÚÜÑ0-9 .'\-]+"
            r"(?:\s+\((?:V\.O\.|O\.S\.|CONT'D|CONTINUED)\))?$"
        )

        return re.fullmatch(character_pattern, line) is not None
    