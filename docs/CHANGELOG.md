# ADÜMN — Changelog

## 16-10-2026

- Fix: la regex de heading ya no parte nombres con guión (ej: `ANA-MARÍA`).
- Fix: `/resources` y CSV ya excluyen los items con `state=rejected`.
- Fix: `shoot_rate_seconds` validado (entre 1 y 3600 segundos).
- Add: endpoints `GET`/`PUT` de aliases de personaje.
- Add: 23 tests nuevos (total: 329).

## 14-10-2026

- Add: helper `parse_character_cue` con VO y combined cues.
- Add: `resolve_character_alias` + tabla `character_aliases`.
- Add: integración de aliases en `list_project_characters`.
- Add: 17 tests nuevos (total: 306).

## 13-10-2026

- Add: endpoint `GET /api/projects/{id}/reports/breakdown`.
- Add: backup integrado (SQLite + imágenes) verificado y restauración probada.
- Add: 6 tests nuevos.