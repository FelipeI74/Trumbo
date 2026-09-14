"""
Trumbo Engine

Production element catalog.

Defines known production elements and their categories.
"""

from engine.core.types.production_element_type import (
    ProductionElementType,
)

PRODUCTION_CATALOG = {

    # ==========================
    # PROPS
    # ==========================

    "teléfono": ProductionElementType.PROP,
    "auricular": ProductionElementType.PROP,
    "vaso": ProductionElementType.PROP,
    "vasos": ProductionElementType.PROP,
    "botella": ProductionElementType.PROP,
    "botellas": ProductionElementType.PROP,
    "copa": ProductionElementType.PROP,
    "copas": ProductionElementType.PROP,
    "cigarro": ProductionElementType.PROP,
    "cigarrillo": ProductionElementType.PROP,
    "encendedor": ProductionElementType.PROP,
    "llave": ProductionElementType.PROP,
    "llaves": ProductionElementType.PROP,
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

    "caja": ProductionElementType.PROP,
    "cajas": ProductionElementType.PROP,
    "caja de herramientas": ProductionElementType.PROP,
    "sartén": ProductionElementType.PROP,
    "sarten": ProductionElementType.PROP,
    "sartenes": ProductionElementType.PROP,
    "huevo": ProductionElementType.PROP,
    "huevos": ProductionElementType.PROP,
    "vela": ProductionElementType.PROP,
    "velas": ProductionElementType.PROP,
    "moneda": ProductionElementType.PROP,
    "monedas": ProductionElementType.PROP,
    "taza": ProductionElementType.PROP,
    "tazas": ProductionElementType.PROP,
    "té": ProductionElementType.PROP,
    "te": ProductionElementType.PROP,
    "loza": ProductionElementType.PROP,
    "cadena": ProductionElementType.PROP,
    "cadenas": ProductionElementType.PROP,

    "plato": ProductionElementType.PROP,
    "platos": ProductionElementType.PROP,
    "cuchillo": ProductionElementType.PROP,
    "cuchillos": ProductionElementType.PROP,
    "tenedor": ProductionElementType.PROP,
    "tenedores": ProductionElementType.PROP,
    "cuchara": ProductionElementType.PROP,
    "cucharas": ProductionElementType.PROP,
    "olla": ProductionElementType.PROP,
    "ollas": ProductionElementType.PROP,
    "tetera": ProductionElementType.PROP,
    "cafetera": ProductionElementType.PROP,
    "bandeja": ProductionElementType.PROP,
    "bandejas": ProductionElementType.PROP,
    "servilleta": ProductionElementType.PROP,
    "servilletas": ProductionElementType.PROP,

    "tv": ProductionElementType.PROP,
    "televisor": ProductionElementType.PROP,
    "televisores": ProductionElementType.PROP,
    "televisión": ProductionElementType.PROP,
    "television": ProductionElementType.PROP,

    # ==========================
    # FURNITURE
    # ==========================

    "mesa": ProductionElementType.FURNITURE,
    "escritorio": ProductionElementType.FURNITURE,
    "silla": ProductionElementType.FURNITURE,
    "sillas": ProductionElementType.FURNITURE,
    "silla plegable": ProductionElementType.FURNITURE,
    "sillas plegables": ProductionElementType.FURNITURE,
    "sofá": ProductionElementType.FURNITURE,
    "sofa": ProductionElementType.FURNITURE,
    "sillón": ProductionElementType.FURNITURE,
    "sillon": ProductionElementType.FURNITURE,
    "estante": ProductionElementType.FURNITURE,
    "librero": ProductionElementType.FURNITURE,
    "cama": ProductionElementType.FURNITURE,
    "velador": ProductionElementType.FURNITURE,
    "colchón": ProductionElementType.FURNITURE,
    "colchon": ProductionElementType.FURNITURE,
    "colchones": ProductionElementType.FURNITURE,
    "colchón inflable": ProductionElementType.FURNITURE,
    "colchon inflable": ProductionElementType.FURNITURE,

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
    "camiones": ProductionElementType.VEHICLE,
    "jeep": ProductionElementType.VEHICLE,
    "jeeps": ProductionElementType.VEHICLE,
    "bus": ProductionElementType.VEHICLE,
    "buses": ProductionElementType.VEHICLE,
    "micro": ProductionElementType.VEHICLE,
    "bicicleta": ProductionElementType.VEHICLE,
    "bicicletas": ProductionElementType.VEHICLE,
    "motocicleta": ProductionElementType.VEHICLE,
    "motocicletas": ProductionElementType.VEHICLE,
    "camioneta": ProductionElementType.VEHICLE,
    "camionetas": ProductionElementType.VEHICLE,
    "furgoneta": ProductionElementType.VEHICLE,
    "furgonetas": ProductionElementType.VEHICLE,
    "taxi": ProductionElementType.VEHICLE,
    "taxis": ProductionElementType.VEHICLE,
    "suv": ProductionElementType.VEHICLE,
    "suvs": ProductionElementType.VEHICLE,
    "furgón": ProductionElementType.VEHICLE,
    "furgon": ProductionElementType.VEHICLE,
    "furgones": ProductionElementType.VEHICLE,
    "van": ProductionElementType.VEHICLE,
    "vans": ProductionElementType.VEHICLE,
    "minibús": ProductionElementType.VEHICLE,
    "minibus": ProductionElementType.VEHICLE,
    "minibuses": ProductionElementType.VEHICLE,
    "moto": ProductionElementType.VEHICLE,
    "motos": ProductionElementType.VEHICLE,
    "ambulancia": ProductionElementType.VEHICLE,
    "ambulancias": ProductionElementType.VEHICLE,
    "patrulla": ProductionElementType.VEHICLE,
    "patrullas": ProductionElementType.VEHICLE,
    "tractor": ProductionElementType.VEHICLE,
    "tractores": ProductionElementType.VEHICLE,
    "tren": ProductionElementType.VEHICLE,
    "tranvía": ProductionElementType.VEHICLE,
    "tranvia": ProductionElementType.VEHICLE,
    "barco": ProductionElementType.VEHICLE,
    "lancha": ProductionElementType.VEHICLE,
    "velero": ProductionElementType.VEHICLE,
    "yate": ProductionElementType.VEHICLE,
    "helicóptero": ProductionElementType.VEHICLE,
    "helicoptero": ProductionElementType.VEHICLE,
    "avión": ProductionElementType.VEHICLE,
    "avion": ProductionElementType.VEHICLE,
    "avioneta": ProductionElementType.VEHICLE,
    "jet": ProductionElementType.VEHICLE,
    "bote": ProductionElementType.VEHICLE,

    # ==========================
    # WARDROBE
    # ==========================

    "abrigo": ProductionElementType.WARDROBE,
    "chaqueta": ProductionElementType.WARDROBE,
    "sombrero": ProductionElementType.WARDROBE,
    "uniforme": ProductionElementType.WARDROBE,
    "casco": ProductionElementType.WARDROBE,
    "vestido": ProductionElementType.WARDROBE,
    "traje": ProductionElementType.WARDROBE,
    "corbata": ProductionElementType.WARDROBE,
    "zapatos": ProductionElementType.WARDROBE,
    "botas": ProductionElementType.WARDROBE,
    "camisa": ProductionElementType.WARDROBE,
    "pantalón": ProductionElementType.WARDROBE,
    "pantalon": ProductionElementType.WARDROBE,
    "falda": ProductionElementType.WARDROBE,
    "blusa": ProductionElementType.WARDROBE,
    "bufanda": ProductionElementType.WARDROBE,
    "guantes": ProductionElementType.WARDROBE,
    "cinturón": ProductionElementType.WARDROBE,
    "cinturon": ProductionElementType.WARDROBE,
    "calcetines": ProductionElementType.WARDROBE,
    "medias": ProductionElementType.WARDROBE,
    "sandalias": ProductionElementType.WARDROBE,
    "zapatillas": ProductionElementType.WARDROBE,
    "collar": ProductionElementType.WARDROBE,
    "pulsera": ProductionElementType.WARDROBE,

    # ==========================
    # STUNTS
    # ==========================

    "caída": ProductionElementType.STUNT,
    "caida": ProductionElementType.STUNT,
    "golpe": ProductionElementType.STUNT,
    "golpes": ProductionElementType.STUNT,
    "pelea": ProductionElementType.STUNT,
    "peleas": ProductionElementType.STUNT,
    "atropello": ProductionElementType.STUNT,
    "atropellos": ProductionElementType.STUNT,
    "arrastre": ProductionElementType.STUNT,
    "arrastres": ProductionElementType.STUNT,
    "lanzamiento": ProductionElementType.STUNT,
    "lanzamientos": ProductionElementType.STUNT,

    # ==========================
    # SPECIAL EFFECTS
    # ==========================

    "explosión": ProductionElementType.SPECIAL_EFFECT,
    "explosion": ProductionElementType.SPECIAL_EFFECT,
    "humo": ProductionElementType.SPECIAL_EFFECT,
    "fuego": ProductionElementType.SPECIAL_EFFECT,
    "lluvia": ProductionElementType.SPECIAL_EFFECT,
    "sangre": ProductionElementType.SPECIAL_EFFECT,
    "niebla": ProductionElementType.SPECIAL_EFFECT,
    "neblina": ProductionElementType.SPECIAL_EFFECT,
    "nieve": ProductionElementType.SPECIAL_EFFECT,
    "viento": ProductionElementType.SPECIAL_EFFECT,
    "relámpago": ProductionElementType.SPECIAL_EFFECT,
    "relampago": ProductionElementType.SPECIAL_EFFECT,
    "trueno": ProductionElementType.SPECIAL_EFFECT,
    "rayo": ProductionElementType.SPECIAL_EFFECT,
    "chispa": ProductionElementType.SPECIAL_EFFECT,
    "chispas": ProductionElementType.SPECIAL_EFFECT,
    "detonación": ProductionElementType.SPECIAL_EFFECT,
    "detonacion": ProductionElementType.SPECIAL_EFFECT,

    # ==========================
    # EXTRAS
    # ==========================

    "extra": ProductionElementType.EXTRA,
    "extras": ProductionElementType.EXTRA,
    "figurante": ProductionElementType.EXTRA,
    "figurantes": ProductionElementType.EXTRA,

    # ==========================
    # ANIMALS
    # ==========================

    "perro": ProductionElementType.ANIMAL,
    "perros": ProductionElementType.ANIMAL,
    "gato": ProductionElementType.ANIMAL,
    "gatos": ProductionElementType.ANIMAL,
    "caballo": ProductionElementType.ANIMAL,
    "caballos": ProductionElementType.ANIMAL,
    "vaca": ProductionElementType.ANIMAL,
    "vacas": ProductionElementType.ANIMAL,
    "toro": ProductionElementType.ANIMAL,
    "toros": ProductionElementType.ANIMAL,
    "oveja": ProductionElementType.ANIMAL,
    "ovejas": ProductionElementType.ANIMAL,
    "cerdo": ProductionElementType.ANIMAL,
    "cerdos": ProductionElementType.ANIMAL,
    "gallina": ProductionElementType.ANIMAL,
    "gallinas": ProductionElementType.ANIMAL,
    "gallo": ProductionElementType.ANIMAL,
    "gallos": ProductionElementType.ANIMAL,
    "pato": ProductionElementType.ANIMAL,
    "patos": ProductionElementType.ANIMAL,
    "burro": ProductionElementType.ANIMAL,
    "burros": ProductionElementType.ANIMAL,
    "conejo": ProductionElementType.ANIMAL,
    "conejos": ProductionElementType.ANIMAL,
    "serpiente": ProductionElementType.ANIMAL,
    "serpientes": ProductionElementType.ANIMAL,

    # ==========================
    # MAKEUP
    # ==========================

    "maquillaje": ProductionElementType.MAKEUP,
    "prótesis": ProductionElementType.MAKEUP,
    "protesis": ProductionElementType.MAKEUP,
    "peluca": ProductionElementType.MAKEUP,
    "pelucas": ProductionElementType.MAKEUP,
    "herida": ProductionElementType.MAKEUP,
    "heridas": ProductionElementType.MAKEUP,
    "cicatriz": ProductionElementType.MAKEUP,
    "cicatrices": ProductionElementType.MAKEUP,
    "moretón": ProductionElementType.MAKEUP,
    "moreton": ProductionElementType.MAKEUP,
    "moretones": ProductionElementType.MAKEUP,
    "caracterización": ProductionElementType.MAKEUP,
    "caracterizacion": ProductionElementType.MAKEUP,
    "barba postiza": ProductionElementType.MAKEUP,
    "bigote postizo": ProductionElementType.MAKEUP,

    # ==========================
    # EQUIPMENT
    # ==========================

    "grúa": ProductionElementType.EQUIPMENT,
    "grua": ProductionElementType.EQUIPMENT,
    "grúas": ProductionElementType.EQUIPMENT,
    "gruas": ProductionElementType.EQUIPMENT,
    "dron": ProductionElementType.EQUIPMENT,
    "generador": ProductionElementType.EQUIPMENT,
    "trípode": ProductionElementType.EQUIPMENT,
    "tripode": ProductionElementType.EQUIPMENT,
    "cámara": ProductionElementType.EQUIPMENT,
    "camara": ProductionElementType.EQUIPMENT,
    "micrófono": ProductionElementType.EQUIPMENT,
    "microfono": ProductionElementType.EQUIPMENT,
    "reflector": ProductionElementType.EQUIPMENT,
    "foco": ProductionElementType.EQUIPMENT,
    "claqueta": ProductionElementType.EQUIPMENT,
    "monitor": ProductionElementType.EQUIPMENT,
    "cable": ProductionElementType.EQUIPMENT,
    "arnés": ProductionElementType.EQUIPMENT,
    "arnes": ProductionElementType.EQUIPMENT,
}
