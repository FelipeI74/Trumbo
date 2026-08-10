# Sophocles 2007 reverse-engineering reference for Trumbo

This folder is a static-analysis dossier generated from the user-provided Sophocles 2007 installer. It is intended as a functional and architectural reference for implementing Trumbo.

## Important rule

Do not treat this folder as recovered source code. The original C++ source was not present in the installer. The evidence here comes from PE resources, embedded help indexes, RTTI/class names, command string tables, and static strings from the compiled executable.

Use evidence in this order:

1. `SOPHOCLES_EDITOR_SPEC.md` for editor behavior.
2. `SOPHOCLES_ARCHITECTURE_MAP.md` for internal architectural clues.
3. `SOPHOCLES_FEATURE_MAP.md` for feature/module scope.
4. `data/commands_curated.tsv` for command-level evidence.
5. `data/classes_rtti.txt` and `data/class_categories.json` for compiled class evidence.
6. `data/help_topics_index.txt` for the embedded help/manual topic tree.

## Trumbo implementation rule

When Sophocles already solved a screenplay-editor workflow, preserve its functional behavior unless Felipe explicitly asks for a change. Trumbo's differentiation should come from its Engine, AI, semantic extraction, automatic production knowledge, and later intelligent scheduling—not from needlessly changing proven screenplay-writing ergonomics.

## Do not do

- Do not copy machine code or attempt to transplant compiled routines into Trumbo.
- Do not infer undocumented behavior as fact.
- Do not add dependencies just to imitate Sophocles.
- Do not rewrite the Trumbo Engine merely because Sophocles used a different internal architecture.
- Do not modify more than one editor subsystem per iteration without explicit instruction.

## Static-analysis provenance

- Installer SHA-256: `7ca9fe143d549a57f0ed5bf93070f6f1ef4e1fd1d36d974b30318bdb6bec6d8e`
- Extracted application SHA-256: `3454fb51078d9fd8dab58e6cdba5bf71352ecf1ab43322fce318a245d92e96b2`
- Application: PE32 x86 Windows GUI, compiled April 21 2007.
- Compiler/toolchain evidence: Visual Studio 8 / Visual C++ 2005 ATL/MFC strings and MFC RTTI.

The binary itself and embedded font files are intentionally not included in this Copilot kit.
