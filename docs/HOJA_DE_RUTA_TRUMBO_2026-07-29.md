# Trumbo — Hoja de ruta práctica

Fecha: 29 de julio de 2026
Versión de trabajo: Alpha 0.1 → Alpha 0.2

## Objetivo del día

Mejorar el editor existente sin rediseñar Trumbo desde cero.

El foco de hoy será doble:

1. Estabilizar el guardado y la edición de escenas.
2. Avanzar en el reconocimiento de comandos y estructuras de guion.

## Principios ya decididos

- Trumbo abre directamente con la página en blanco y la interfaz completa.
- El primer comando de entrada es `Crear proyecto`.
- El usuario debe sentir que avanzar es fácil.
- Trumbo no impone un método de escritura.
- La IA se usa como asistente para resumir, ordenar, detectar y analizar; no para reemplazar decisiones creativas.
- El guion permanece como centro de la experiencia.
- La escena es la unidad viva del proyecto.
- La interfaz actual se mejora; no se reemplaza.

## Prioridad 1 — Guardado confiable

### Trabajo

- Revisar por qué aparece `Error al guardar`.
- Confirmar que el autoguardado funciona en encabezado, cuerpo y sinopsis.
- Mantener estados visibles:
  - Editando…
  - Guardando…
  - Guardado
  - Error al guardar
- Evitar que una edición pendiente se pierda al cambiar de escena.
- Mostrar un error más útil en consola y, si corresponde, en la interfaz.

### Resultado esperado

El usuario puede escribir, cambiar de escena y volver sin perder texto.

## Prioridad 2 — Reconocimiento de comandos del guion

### Alcance inicial

Trumbo debe comenzar a reconocer los elementos básicos del formato cinematográfico dentro del texto:

- Encabezado de escena:
  - `INT.`
  - `EXT.`
  - `INT/EXT.`
  - `EXT/INT.`
- Acción.
- Nombre de personaje.
- Diálogo.
- Acotación o parentético.
- Transición.
- Indicaciones especiales habituales, como:
  - `CONTINUO`
  - `MÁS TARDE`
  - `DÍA`
  - `NOCHE`
  - `CORTE A:`
  - `FUNDIDO A:`

### Primera meta técnica

Crear una función de análisis que reciba el cuerpo de una escena y devuelva bloques identificados, por ejemplo:

```text
heading
action
character
parenthetical
dialogue
transition
```

### Regla

Durante esta primera etapa, Trumbo puede sugerir o reconocer. No debe modificar automáticamente lo escrito por el usuario sin confirmación.

### Resultado esperado

Al escribir una escena, Trumbo identifica correctamente al menos:

- encabezado,
- acción,
- personaje,
- diálogo.

## Prioridad 3 — Pruebas

Agregar pruebas para verificar:

- reconocimiento de encabezados,
- reconocimiento de personajes,
- diferenciación entre acción y diálogo,
- escenas sin diálogo,
- encabezados con `INT/EXT.`,
- nombres de personajes con tildes y espacios,
- textos que no deben confundirse con personajes.

## Orden práctico de trabajo

1. Ejecutar la versión actual.
2. Reproducir el error de guardado.
3. Corregir el error.
4. Hacer una prueba manual de creación y edición de escenas.
5. Crear el analizador básico de comandos.
6. Agregar pruebas automáticas.
7. Integrar el reconocimiento al editor sin alterar todavía el diseño visual.
8. Hacer commit.
9. Subir a GitHub.

## Criterio de cierre del día

La jornada se considera exitosa si:

- el autoguardado funciona sin pérdida de datos;
- Trumbo reconoce los cuatro bloques esenciales del guion;
- las pruebas pasan;
- los cambios quedan registrados en Git y GitHub.

## Commit sugerido

```bash
git add .
git commit -m "Alpha 0.2 - mejora guardado y reconocimiento basico de guion"
git push
```

## Pendientes posteriores

No abordar hoy, salvo que sobre tiempo:

- reordenar escenas;
- duplicar escenas;
- eliminar escenas;
- recuperar revisiones anteriores;
- storyboard por escena;
- desglose automático completo;
- asistente IA general;
- plan de rodaje.

## Registro al finalizar

Completar al terminar la jornada:

### Avances realizados

- 

### Problemas encontrados

- 

### Decisiones tomadas

- 

### Próximo paso exacto

- 
