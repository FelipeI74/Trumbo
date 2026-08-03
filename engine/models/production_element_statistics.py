"""
Trumbo Engine

Model: Production Element Statistics
"""

from dataclasses import dataclass

from engine.core.production_element import ProductionElement


@dataclass
class ProductionElementStatistics:
    """
    Represents the participation of a production element
    within the analyzed screenplay.
    """

    element: ProductionElement

    first_scene_id: str

    appearance_count: int = 0
