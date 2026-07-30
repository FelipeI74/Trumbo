"""
Trumbo Engine

Core entity: Location
"""

from dataclasses import dataclass


@dataclass
class Location:
    """
    Represents a narrative location detected in the screenplay.

    Production and scouting information can later be attached
    through a dedicated location sheet.
    """

    id: str
    name: str
