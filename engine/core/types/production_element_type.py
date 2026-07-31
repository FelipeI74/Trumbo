"""
Trumbo Engine

Production element categories.
"""

from enum import Enum


class ProductionElementType(str, Enum):

    PROP = "prop"

    SET_DRESSING = "set_dressing"

    FURNITURE = "furniture"

    VEHICLE = "vehicle"

    WARDROBE = "wardrobe"

    SPECIAL_EFFECT = "special_effect"

    UNKNOWN = "unknown"
    