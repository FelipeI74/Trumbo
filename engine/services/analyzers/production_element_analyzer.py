"""
Trumbo Engine

Analyzer: Production Element Analyzer
"""

import re
from uuid import uuid4

from engine.catalogs.production_catalog import PRODUCTION_CATALOG
from engine.core.block import Block
from engine.core.production_element import ProductionElement
from engine.core.types.block_type import BlockType


class ProductionElementAnalyzer:
    """
    Detect known production elements inside ACTION blocks.

    The analyzer only recognizes complete words or expressions
    contained in the production catalog.
    """

    def extract(
        self,
        blocks: list[Block],
    ) -> list[ProductionElement]:
        """
        Return unique production elements found in ACTION blocks.
        """

        elements: dict[str, ProductionElement] = {}

        for block in blocks:
            if block.block_type != BlockType.ACTION:
                continue

            text = block.content.lower()

            for name, category in PRODUCTION_CATALOG.items():
                if not self._contains_element(text, name):
                    continue

                key = name.lower()

                if key in elements:
                    continue

                elements[key] = ProductionElement(
                    id=str(uuid4()),
                    name=name.capitalize(),
                    element_type=category,
                )

        return sorted(
            elements.values(),
            key=lambda element: element.name,
        )

    def _contains_element(
        self,
        text: str,
        element_name: str,
    ) -> bool:
        """
        Return True only when the complete element name appears.

        This prevents 'papel' from matching inside 'papeles'.
        """

        pattern = rf"(?<!\w){re.escape(element_name.lower())}(?!\w)"

        return re.search(pattern, text) is not None
    