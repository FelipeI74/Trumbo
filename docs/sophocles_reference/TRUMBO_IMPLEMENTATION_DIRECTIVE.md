# Directive for Copilot when implementing Trumbo from the Sophocles reference

## Product target

Recreate the practical screenplay-and-production workflow of Sophocles with a modern implementation, then extend it with the Trumbo Engine and AI.

## First principle

Do not invent a new screenplay workflow when Sophocles already provides a proven one.

## Implementation order

1. Screenplay editor behavior
2. Scene/Explorer derivation
3. Character/Location/Resource explorers
4. Breakdown
5. Engine-driven automatic proposals
6. Scheduling
7. AI-assisted scheduling/continuity/production

## Editor implementation

Before changing keyboard, paragraph type, scene derivation, or Explorer behavior:

1. Read `SOPHOCLES_EDITOR_SPEC.md`.
2. Search `data/commands_curated.tsv` for direct command evidence.
3. Search `data/help_topics_index.txt` for the relevant manual topic.
4. Consult Felipe if exact behavior remains ambiguous.
5. Change one subsystem only.
6. Run tests.
7. Require manual validation before moving on.
8. Commit/checkpoint the validated state before the next subsystem.

## Scene model

Do not maintain a visual Scene list independently of the screenplay.

Preferred model:

```text
Document
  -> semantic paragraph types
  -> valid scene headings
  -> derived/persisted Scene entities
  -> Explorer projection
```

Editing/removing a heading must update the same project model and therefore the Explorer.

## Engine integration

The Trumbo Engine should enhance, not replace, the screenplay workflow.

Examples:

- Sophocles: user assigns resources to scene.
- Trumbo: Engine detects/proposes resources; user confirms.

- Sophocles: user builds schedule with constraints/tools.
- Trumbo: same production model plus AI-generated schedule alternatives and optimization suggestions.

## Do not use this dossier as source code

This is reverse-engineering evidence, not the original source tree. Implement cleanly in Trumbo's language/framework.
