"""
Trumbo Engine

Core entity: Scene
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Scene:
    """
    Represents a screenplay scene.

    The scene heading is generated from its structured fields
    to avoid inconsistencies between stored data and displayed text.
    """

    id: str
    number: str
    interior_exterior: str
    general_location: str
    specific_location: Optional[str]
    time_of_day: str
    content: str

    @property
    def heading(self) -> str:
        """
        Build the complete screenplay heading.
        """

        parts = [
            f"{self.interior_exterior}.",
            self.general_location,
        ]

        if self.specific_location:
            parts.append(self.specific_location)

        parts.append(self.time_of_day)

        return " - ".join(parts).upper()

    def is_interior(self) -> bool:
        """
        Return True when the scene is interior.
        """

        return self.interior_exterior.upper() == "INT"

    def is_exterior(self) -> bool:
        """
        Return True when the scene is exterior.
        """

        return self.interior_exterior.upper() == "EXT"

    def is_night(self) -> bool:
        """
        Return True when the scene takes place at night.
        """

        return self.time_of_day.upper() == "NOCHE"
