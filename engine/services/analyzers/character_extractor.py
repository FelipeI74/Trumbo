"""
Trumbo Engine

Analyzer: Character Extractor
"""

from uuid import uuid4

from core.character import Character
from core.event import Event
from models.character_statistics import CharacterStatistics


class CharacterExtractor:
    """
    Extract unique characters from screenplay events.

    The extractor counts how many events involve each character
    and records the first scene where the character appears.
    """

    def extract(
        self,
        events: list[Event],
    ) -> list[CharacterStatistics]:
        """
        Build character statistics from Event subjects.
        """

        characters: dict[str, CharacterStatistics] = {}

        for event in events:
            if not event.subject:
                continue

            name = event.subject.strip()

            if not name:
                continue

            key = name.upper()

            if key not in characters:
                character = Character(
                    id=str(uuid4()),
                    name=name,
                )

                characters[key] = CharacterStatistics(
                    character=character,
                    first_scene_id=event.scene_id,
                    event_count=1,
                )

                continue

            characters[key].event_count += 1

        return sorted(
            characters.values(),
            key=lambda item: item.character.name.upper(),
        )