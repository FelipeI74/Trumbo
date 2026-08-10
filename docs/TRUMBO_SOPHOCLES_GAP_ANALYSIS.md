# TRUMBO_SOPHOCLES_GAP_ANALYSIS

Fecha: 2026-08-10

## A. Arquitectura funcional relevante de Sophocles

### Núcleo funcional observado
- Documento de guion como fuente primaria.
- Tipos de párrafo explícitos: Scene Heading, Action, Cue, Dialogue, Parenthetical, Transition-In, Transition-Out.
- Auto-Type y Auto-Convert como subsistemas editoriales dedicados.
- Explorers como proyecciones sincronizadas del documento/modelo (Scene/Header, Character, Location, Resource, Thread/Timeline).
- Spell check y thesaurus como subsistema real (no solo atributo visual).
- Breakdown, Resources y Scheduling integrados con el mismo modelo de proyecto.
- Auto-Schedule como herramienta sobre datos de producción ya estructurados.

### Evidencia usada
- SOPHOCLES_EDITOR_SPEC.md
- SOPHOCLES_ARCHITECTURE_MAP.md
- SOPHOCLES_FEATURE_MAP.md
- TRUMBO_IMPLEMENTATION_DIRECTIVE.md
- data/commands_curated.tsv
- data/editor_autotype_clues.txt
- data/editor_autoconvert_clues.txt
- data/help_topics_index.txt (índice de temas)

## B. Arquitectura REAL actual de Trumbo

### Modelo actual visible
- Backend FastAPI con proyectos/escenas persistidos en SQLite.
- API principal:
  - POST /api/projects (crea proyecto sin escenas)
  - GET /api/projects/{id} (devuelve project + scenes)
  - POST /api/projects/{id}/scenes (crea escena)
  - PATCH /api/scenes/{id} (actualiza heading/body/semantic_lines/synopsis)
  - DELETE /api/scenes/{id} (elimina y renumera)
- Frontend usa state.scenes como fuente para Scene Explorer lateral.
- Documento continuo del editor puede existir:
  - como borrador sin escenas persistidas (líneas sueltas), o
  - como escenas persistidas (bloques .script-scene).

### Flujo funcional real hoy
- Documento → tipos de línea (inferLineType + setLineType + handlers de input/keydown/paste).
- Headings detectados por prefijo INT./EXT. y criterios de “heading completo”.
- Escenas se crean por rutas múltiples (no un pipeline único).
- Explorer se pinta desde state.scenes.
- Persistencia se hace por saveSceneNode y llamadas API por escena.

## C. Comparación lado a lado

| Tema | Sophocles referencia | Trumbo actual |
|---|---|---|
| Fuente de verdad | Documento/modelo único, explorers sincronizados | Mezcla documento + state.scenes + correcciones post hoc |
| Tipos de línea | Subsistema estable de párrafos | Tipos funcionan, pero con múltiples rutas de conversión/split |
| Escena desde heading | Regla editor-modelo consistente | Reglas repartidas entre input/enter/paste/split/materialize/collapse |
| Explorer | Proyección del modelo actual | Proyección de state.scenes; puede desfasarse del documento en bordes |
| Spell check | Subsistema explícito | Dependencia del spellcheck nativo del navegador |
| Keyboard ergonomía | Comandos claros (Tab/Enter, Auto-Type) | Parcialmente alineado, con regresiones intermitentes |
| Breakdown/Schedule | Integrados | Breakdown existente; schedule no implementado en frontend actual |

## D. Regresiones detectadas

1. Escenas fantasma en Explorer.
- Pueden aparecer entradas que ya no corresponden al documento visible.

2. FADE IN tratado como escena en casos de datos heredados/inconsistentes.
- Síntoma reportado manualmente: Scene card con FADE IN como título.

3. Derivación de escenas dependiente del momento del evento de teclado.
- El resultado cambia según si el heading llega por input progresivo, Enter o paste.

4. Ortografía no confiable en UX final.
- Puede subrayar pero no ofrecer sugerencias contextuales de forma consistente.

## E. Duplicaciones/contradicciones del editor actual

El mismo problema (derivar/sincronizar escenas) se intenta resolver por caminos distintos en app/static/app.js:

1. materializeScenesFromDraftDocument
- Convierte documento borrador completo a escenas persistidas.

2. splitSceneAtHeading
- Parte una escena existente al encontrar heading interno.

3. ensureSceneStructure
- Recorre headings extra y dispara split adicional.

4. handleLineInput
- Convierte tipos y puede gatillar rutas de escena indirectas.

5. handleLinePaste
- Inserta múltiples líneas y también puede activar split/materialize.

6. maybeCollapseSceneWithoutHeading + mergeSceneIntoPrevious
- Corrigen posteriori escenas sin heading.

7. collapseLeadingHeadinglessScene
- Normalización extra para escena inicial sin heading.

Conclusión:
- Existe superposición funcional y ordenes de ejecución que compiten entre sí.
- El sistema funciona en casos felices, pero tiene puntos de carrera y desalineación modelo-vista.

## F. Qué conservar

1. Contratos backend actuales de project/scene, incluyendo PATCH con semantic_lines.
2. Engine y adapter de análisis ya integrados en panel de desglose.
3. Modelo de líneas semánticas del frontend.
4. Rutas de guardado con control de revisiones por escena.
5. Regla de proyecto nuevo con 0 escenas persistidas.
6. Identidad visual moderna de Trumbo.

## G. Qué corregir

1. Unificar derivación de escenas en una sola estrategia determinista.
- Regla: Explorer debe derivar del mismo estado estructural que persiste.
- Evitar derivaciones alternativas en paralelo.

2. Definir explícitamente “heading válido de escena”.
- Solo INT./EXT. según regla de producto.
- Todo lo demás (incluyendo FADE IN) no crea escena.

3. Separar claramente:
- Conversión de tipo de línea (editor),
- Delimitación de escena (modelo),
- Persistencia (API),
- Proyección (Explorer).

4. Consolidar limpieza de escenas sin heading en un solo punto de verdad.
- No múltiples “parches” correctivos tardíos.

5. Spellcheck:
- Mantener nativo como temporal, pero aceptar que no garantiza UX homogénea.
- Si se exige fiabilidad tipo producto, planificar subsistema dedicado (como Sophocles).

## H. Qué NO tocar

1. Engine (analyzers, parser, extracción semántica de producción).
2. Contratos semánticos backend ya usados por frontend y tests.
3. Base SQLite/esquema fuera de lo estrictamente necesario para contratos ya en uso.
4. Identidad visual principal (no imitar estética 2007).
5. Tests existentes correctos.

## I. Orden recomendado de implementación

1. Congelar comportamiento de creación/delimitación de escenas en un módulo único del frontend.
2. Definir función pura de derivación Documento → Escenas (basada en tipos de línea ya existentes).
3. Aplicar esa derivación de forma uniforme para input, Enter, paste y carga.
4. Sincronizar Explorer solo desde ese resultado derivado.
5. Persistir diferencias (crear/actualizar/eliminar) en lote ordenado y estable.
6. Recién después, ajustar ergonomía fina de teclado.
7. Finalmente, estabilizar spellcheck con decisión explícita: nativo temporal o subsistema dedicado.

## J. Riesgos de regresión

1. Duplicación de escenas por rutas de split/materialize concurrentes.
2. Escenas huérfanas en backend que reaparezcan al recargar.
3. Pérdida de caret/foco al mezclar delimitación de escena con edición en vivo.
4. Sobrescritura de semantic_lines por guardados fuera de orden.
5. Falsos headings por auto-convert demasiado amplio.
6. Confusión del usuario entre “documento visible” y “explorer persistido”.

## Diagnóstico específico solicitado

### 1) Comportamientos de Sophocles ya presentes en Trumbo
- Tipos de párrafo centrales de guion.
- Reconocimiento de transiciones básicas.
- Flujo general de Tab/Enter aproximado.
- Explorer de escenas y paneles de producción.

### 2) Comportamientos presentes pero distintos
- Spellcheck en Trumbo depende de navegador; Sophocles lo trata como subsistema.
- Auto-Convert/Auto-Type en Trumbo está distribuido en lógica ad hoc; en Sophocles es más declarativo.

### 3) Comportamientos de Trumbo actualmente rotos
- Sincronización totalmente confiable Documento ↔ Scenes ↔ Explorer.
- Consistencia de eliminación real de escenas fantasma en todos los caminos.

### 4) Funcionalidades que Trumbo logró y luego regresaron
- Escena inicial de proyecto sin escena persistida quedó correcta, pero se introdujeron rutas compensatorias que reabren inconsistencias en casos borde.

### 5) Partes de app.js resolviendo lo mismo por vías distintas
- materializeScenesFromDraftDocument
- splitSceneAtHeading
- ensureSceneStructure
- handleLineInput
- handleLinePaste
- maybeCollapseSceneWithoutHeading
- collapseLeadingHeadinglessScene

### 6) Flujo real hoy
Documento
→ inferencia/conversión de tipo por línea
→ eventos de split/materialización según contexto
→ state.scenes parcial o total
→ persistencia por escena
→ Explorer renderizado desde state.scenes

### 7) Por qué puede haber varios INT./EXT. y 0 escenas
- Cuando el documento está en modo borrador (sin .script-scene persistidas), hay headings visuales pero state.scenes aún vacío.
- Si la materialización no se dispara en ese camino/evento específico, Explorer sigue en 0.

### 8) Arquitectura de Sophocles relevante sin reescribir engine/backend
- Mantener documento/modelo como fuente de verdad única para explorar/derivar.
- Resolver escenas como proyección determinista del documento, no por handlers dispersos.

### 9) Código actual a conservar
- Contratos API de escenas/proyectos.
- Save pipeline por escena con revisiones.
- Integración del panel de análisis con Engine.

### 10) Código a simplificar/sustituir/eliminar
- Consolidar rutas paralelas de derivación/split/collapse.
- Reducir correcciones tardías (parches de normalización) en favor de derivación única.
- Limpiar condiciones duplicadas en handlers de teclado/input.
