"""
Trumbo Engine

Production element catalog.

Defines known production elements and their categories.
"""

from core.types.production_element_type import (
    ProductionElementType,
)

PRODUCTION_CATALOG = {

    # ==========================
    # PROPS
    # ==========================

    "teléfono": ProductionElementType.PROP,
    "auricular": ProductionElementType.PROP,
    "vaso": ProductionElementType.PROP,
    "botella": ProductionElementType.PROP,
    "copa": ProductionElementType.PROP,
    "cigarro": ProductionElementType.PROP,
    "cigarrillo": ProductionElementType.PROP,
    "encendedor": ProductionElementType.PROP,
    "llaves": ProductionElementType.PROP,
    "llave": ProductionElementType.PROP,
    "cartera": ProductionElementType.PROP,
    "bolso": ProductionElementType.PROP,
    "mochila": ProductionElementType.PROP,
    "libro": ProductionElementType.PROP,
    "revista": ProductionElementType.PROP,
    "diario": ProductionElementType.PROP,
    "periódico": ProductionElementType.PROP,
    "papel": ProductionElementType.PROP,
    "papeles": ProductionElementType.PROP,
    "carta": ProductionElementType.PROP,
    "lápiz": ProductionElementType.PROP,
    "lapiz": ProductionElementType.PROP,
    "pluma": ProductionElementType.PROP,
    "cuaderno": ProductionElementType.PROP,
    "maleta": ProductionElementType.PROP,
    "reloj": ProductionElementType.PROP,

    # ==========================
    # FURNITURE
    # ==========================

    "mesa": ProductionElementType.FURNITURE,
    "escritorio": ProductionElementType.FURNITURE,
    "silla": ProductionElementType.FURNITURE,
    "sofá": ProductionElementType.FURNITURE,
    "sofa": ProductionElementType.FURNITURE,
    "sillón": ProductionElementType.FURNITURE,
    "sillon": ProductionElementType.FURNITURE,
    "estante": ProductionElementType.FURNITURE,
    "librero": ProductionElementType.FURNITURE,
    "cama": ProductionElementType.FURNITURE,
    "velador": ProductionElementType.FURNITURE,

    # ==========================
    # SET DRESSING
    # ==========================

    "puerta": ProductionElementType.SET_DRESSING,
    "ventana": ProductionElementType.SET_DRESSING,
    "escalera": ProductionElementType.SET_DRESSING,
    "muro": ProductionElementType.SET_DRESSING,
    "pared": ProductionElementType.SET_DRESSING,
    "techo": ProductionElementType.SET_DRESSING,
    "piso": ProductionElementType.SET_DRESSING,
    "mostrador": ProductionElementType.SET_DRESSING,
    "barra": ProductionElementType.SET_DRESSING,

    # ==========================
    # VEHICLES
    # ==========================

    "auto": ProductionElementType.VEHICLE,
    "automóvil": ProductionElementType.VEHICLE,
    "automovil": ProductionElementType.VEHICLE,
    "camión": ProductionElementType.VEHICLE,
    "camion": ProductionElementType.VEHICLE,
    "jeep": ProductionElementType.VEHICLE,
    "bus": ProductionElementType.VEHICLE,
    "micro": ProductionElementType.VEHICLE,
    "bicicleta": ProductionElementType.VEHICLE,
    "motocicleta": ProductionElementType.VEHICLE,
    "helicóptero": ProductionElementType.VEHICLE,
    "helicoptero": ProductionElementType.VEHICLE,
    "avión": ProductionElementType.VEHICLE,
    "avion": ProductionElementType.VEHICLE,
    "bote": ProductionElementType.VEHICLE,

    # ==========================
    # WARDROBE
    # ==========================

    "abrigo": ProductionElementType.WARDROBE,
    "chaqueta": ProductionElementType.WARDROBE,
    "sombrero": ProductionElementType.WARDROBE,
    "uniforme": ProductionElementType.WARDROBE,
    "casco": ProductionElementType.WARDROBE,

    # ==========================
    # SPECIAL EFFECTS
    # ==========================

    "explosión": ProductionElementType.SPECIAL_EFFECT,
    "explosion": ProductionElementType.SPECIAL_EFFECT,
    "humo": ProductionElementType.SPECIAL_EFFECT,
    "fuego": ProductionElementType.SPECIAL_EFFECT,
    "lluvia": ProductionElementType.SPECIAL_EFFECT,
    "sangre": ProductionElementType.SPECIAL_EFFECT,
}
