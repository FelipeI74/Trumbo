"""
Trumbo Engine

Extracts structured events from screenplay blocks.
"""

import re
from uuid import uuid4

from engine.core.block import Block
from engine.core.event import Event
from engine.core.types.block_type import BlockType


class EventExtractor:
    """
    Extract structured production events from ACTION blocks.

    This first version uses deterministic rules.
    It does not use AI.
    """

    def extract(
        self,
        blocks: list[Block],
    ) -> list[Event]:
        """
        Convert ACTION blocks into Event objects.

        Each sentence inside an ACTION block becomes one event.
        """

        events: list[Event] = []
        event_order = 1

        for block in blocks:
            if block.block_type != BlockType.ACTION:
                continue

            sentences = self._split_sentences(
                block.content
            )

            for sentence in sentences:
                subject, verb, object_value = (
                    self._extract_action_parts(
                        sentence
                    )
                )

                event = Event(
                    id=str(uuid4()),
                    scene_id=block.scene_id,
                    order=event_order,
                    title=sentence.rstrip("."),
                    summary=sentence,
                    subject=subject,
                    verb=verb,
                    object=object_value,
                )

                events.append(event)
                event_order += 1

        return events

    def _split_sentences(
        self,
        text: str,
    ) -> list[str]:
        """
        Split action text into simple sentences.
        """

        parts = re.split(
            r"(?<=[.!?])\s+",
            text.strip(),
        )

        return [
            part.strip()
            for part in parts
            if part.strip()
        ]

    def _extract_action_parts(
        self,
        sentence: str,
    ) -> tuple[
        str | None,
        str | None,
        str | None,
    ]:
        """
        Extract a basic subject, verb and object.

        Example:
        Ravest abre la puerta.

        subject = Ravest
        verb = abre
        object = la puerta
        """

        cleaned = sentence.strip().rstrip(
            ".!?"
        )

        words = cleaned.split()

        if not words:
            return None, None, None

        subject = words[0]

        if len(words) == 1:
            return subject, None, None

        verb = words[1]

        object_value = (
            " ".join(words[2:])
            if len(words) > 2
            else None
        )

        return subject, verb, object_value