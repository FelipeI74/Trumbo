"""
Trumbo Engine

Production Catalog Service.
"""

from catalogs.production_catalog import (
    PRODUCTION_CATALOG,
)

from core.types.production_element_type import (
    ProductionElementType,
)


class ProductionCatalogService:
    """
    Provides access to the production element catalog.
    """

    def get_category(
        self,
        element_name: str,
    ) -> ProductionElementType:
        """
        Return the category of a production element.

        Unknown elements return UNKNOWN.
        """

        key = element_name.strip().lower()

        return PRODUCTION_CATALOG.get(
            key,
            ProductionElementType.UNKNOWN,
        )

    def exists(
        self,
        element_name: str,
    ) -> bool:
        """
        Return True if the element exists
        in the production catalog.
        """

        key = element_name.strip().lower()

        return key in PRODUCTION_CATALOG
    