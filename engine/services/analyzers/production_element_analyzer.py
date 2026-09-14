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
from engine.core.types.production_element_type import (
    ProductionElementType,
)


class ProductionElementAnalyzer:
    """
    Detect production elements inside ACTION blocks.

    Known elements are detected from the production catalog.
    Simple object enumerations can also produce PROP candidates.
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

            for name, category in sorted(
                PRODUCTION_CATALOG.items(),
                key=lambda item: len(item[0]),
                reverse=True,
            ):
                if not self._contains_element(text, name):
                    continue

                key = name.lower()

                if any(
                    key != existing_key
                    and re.search(
                        rf"(?<!\w){re.escape(key)}(?!\w)",
                        existing_key,
                    )
                    for existing_key in elements
                ):
                    continue

                if key in elements:
                    continue

                elements[key] = ProductionElement(
                    id=str(uuid4()),
                    name=name.capitalize(),
                    element_type=category,
                )

            for candidate in self._extract_enumerated_props(text):
                key = candidate.lower()

                if key in elements:
                    continue

                shorter_keys = [
                    existing_key
                    for existing_key in elements
                    if existing_key != key
                    and re.search(
                        rf"(?<!\w){re.escape(existing_key)}(?!\w)",
                        key,
                    )
                ]

                for shorter_key in shorter_keys:
                    del elements[shorter_key]

                elements[key] = ProductionElement(
                    id=str(uuid4()),
                    name=candidate.capitalize(),
                    element_type=ProductionElementType.PROP,
                )

            for candidate in self._extract_indefinite_props(text):
                key = candidate.lower()

                if key in elements:
                    continue

                elements[key] = ProductionElement(
                    id=str(uuid4()),
                    name=candidate.capitalize(),
                    element_type=ProductionElementType.PROP,
                )

            for candidate in self._extract_effect_candidates(text):
                key = candidate.lower()

                if key in elements:
                    continue

                elements[key] = ProductionElement(
                    id=str(uuid4()),
                    name=candidate,
                    element_type=ProductionElementType.SPECIAL_EFFECT,
                )

            for candidate in self._extract_stunt_candidates(text):
                key = candidate.lower()

                if key in elements:
                    continue

                elements[key] = ProductionElement(
                    id=str(uuid4()),
                    name=candidate,
                    element_type=ProductionElementType.STUNT,
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
        """

        pattern = (
            rf"(?<!\w)"
            rf"{re.escape(element_name.lower())}"
            rf"(?!\w)"
        )

        return re.search(pattern, text) is not None

    def _extract_effect_candidates(
        self,
        text: str,
    ) -> list[str]:
        """
        Detect physical or visual effects from general action patterns.
        """

        effect_patterns = (
            (
                r"\b(?:zorzal|ave|pájaro|pajaro)\b(?:\s+\w+){0,4}\s+"
                r"(?:golpea|choca|impacta)\s+contra\s+(?:su|la|una)\s+ventana\b",
                "Impacto contra ventana",
            ),
            (
                r"\b(?:romp\w*|quebr\w*|part\w*|desgarr\w*|rasg\w*|"
                r"destruy\w*)\b",
                "Efecto de ruptura",
            ),
            (
                r"\b(?:revent\w*|revient\w*|estall\w*|explot\w*|"
                r"(?:hacerse|hace)\s+añicos)\b",
                "Efecto de estallido",
            ),
            (
                r"\b(?:descarg\w*|electrocut\w*|corrient\w*|"
                r"ray\w*|relámpag\w*)\b",
                "Efecto de descarga",
            ),
            (
                r"\b(?:emit\w*|desprend\w*|ilumin\w*|liber\w*|"
                r"expuls\w*)\b",
                "Efecto de emisión",
            ),
            (
                r"\b(?:transform\w*|convert\w*|cambi\w*|derrit\w*|"
                r"congel\w*|quem\w*|ard\w*|incendi\w*)\b",
                "Efecto de transformación",
            ),
        )

        return [
            candidate
            for pattern, candidate in effect_patterns
            if re.search(pattern, text) is not None
        ]

    def _extract_stunt_candidates(
        self,
        text: str,
    ) -> list[str]:
        """
        Detect explicit stunt actions from controlled screenplay patterns.
        """

        stunt_patterns = (
            (r"\b(?:cae|caen|cayó|cayo|cayeron)\b", "Caída"),
            (
                r"\bsale(?:n)?\s+despedido(?:s|a|as)?\b",
                "Persona despedida",
            ),
            (r"\bes\s+arrojad[oa]s?\b", "Persona arrojada"),
            (r"\blo(?:s)?\s+arrastran\b", "Arrastre"),
            (r"\bes\s+atropellad[oa]s?\b", "Atropello"),
            (r"\bse\s+golpea\b", "Golpe"),
        )

        return [
            candidate
            for pattern, candidate in stunt_patterns
            if re.search(pattern, text) is not None
        ]

    def _extract_enumerated_props(
        self,
        text: str,
    ) -> list[str]:
        """
        Detect simple object lists such as:

        'un par de guantes, un martillo y una barreta de fierro'
        """

        candidates: list[str] = []

        sentences = re.split(r"[.!?]+", text)

        for sentence in sentences:
            if "," not in sentence:
                continue

            parts = re.split(
                r"\s*,\s*|\s+y\s+",
                sentence,
            )

            tail = parts[1:]

            detected: list[str] = []

            for part in tail:
                match = re.match(
                    r"^\s*(?:un|una|unos|unas)\s+(.+?)\s*$",
                    part,
                )

                if not match:
                    continue

                candidate = match.group(1).strip()

                candidate = re.sub(
                    r"^par\s+de\s+",
                    "",
                    candidate,
                )

                if candidate:
                    detected.append(candidate)

            if len(detected) >= 2:
                candidates.extend(detected)

        return candidates

    def _extract_indefinite_props(
        self,
        text: str,
    ) -> list[str]:
        """
        Detect unknown plural objects introduced by an indefinite article.

        This keeps discovery independent of the production catalog while
        avoiding common singular subject phrases.
        """

        candidates: list[str] = []
        pattern = (
            r"\b(?:unos|unas)\s+"
            r"([a-záéíóúüñ]+)"
        )

        for match in re.finditer(pattern, text):
            prefix = text[:match.start()]

            if re.search(
                r"(?:durante|por|hace)\s+$",
                prefix,
            ):
                continue

            candidate = match.group(1).strip()

            if candidate and candidate not in candidates:
                candidates.append(candidate)

        return candidates