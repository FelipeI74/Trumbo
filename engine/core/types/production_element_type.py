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

    STUNT = "stunt"

    SPECIAL_EFFECT = "special_effect"

    EXTRA = "extra"

    ANIMAL = "animal"

    MAKEUP = "makeup"

    EQUIPMENT = "equipment"

    UNKNOWN = "unknown"
    