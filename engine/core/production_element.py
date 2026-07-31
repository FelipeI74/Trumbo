"""
Trumbo Engine

Core entity: Production Element
"""

from dataclasses import dataclass

from core.types.production_element_type import (
    ProductionElementType,
)


@dataclass
class ProductionElement:
    """
    Represents a physical production element detected
    inside a screenplay.
    """

    id: str
    name: str
    element_type: ProductionElementType
    