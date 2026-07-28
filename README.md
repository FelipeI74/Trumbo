# Trumbo Alpha 0.1

Primera piedra funcional de Trumbo: un editor de guion centrado en la escena como unidad viva de producción.

## Incluye

- Proyectos
- Escenas ordenadas
- Encabezado, cuerpo y sinopsis por escena
- Duración estimada siempre visible
- Notas
- Elementos de desglose sugeridos o confirmados
- Historial básico de revisiones
- API local
- Persistencia SQLite
- Interfaz web local

## Principio de arquitectura

El guion es el documento maestro.  
La escena es la unidad mínima.  
Los informes son vistas derivadas de los mismos datos.

## Ejecutar

Requiere Python 3.11 o superior.

```bash
cd trumbo-alpha
python -m venv .venv
```

En Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

En macOS o Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Abre `http://127.0.0.1:8000`.

## Pruebas

```bash
python -m unittest discover -s tests
```

## Alcance

Esta versión no resuelve todavía storyboard, stripboard, hojas de llamado ni planificación. Su misión es fijar correctamente el corazón del sistema: Proyecto → Escena → Información derivada.
