# Sophocles 2007 — editor evidence and Trumbo implementation spec

## Evidence from compiled commands

The application contains explicit commands for:

- Insert interior scene header (`Ctrl+I`)
- Insert exterior scene header (`Ctrl+E`)
- Insert empty scene header
- Convert current paragraph to scene header
- Convert current paragraph to action
- Convert current paragraph to dialogue
- Convert current paragraph to dialog cue
- Insert/convert Transition-In
- Insert/convert Transition-Out
- Insert `CUT TO`
- Insert `FADE OUT`
- Insert `DISSOLVE TO`
- Insert `FADE IN`
- Spell Check (`F7`)
- Thesaurus
- paragraph type selection

The compiled editor also contains explicit internal actions/strings for:

- Accept auto-type
- Clear auto-type
- Back to action
- Back to cue
- Action
- Dialogue
- Trans out
- Cue above
- Action above
- Split+Cue
- Start of paragraph
- Delete / Backspace

The options strings contain an `Auto-Convert` section with separate conversion lists for Scene Header, Transition In and Transition Out. Default text evidence includes `int.`, `ext.`, `fade in:`, `fade up:`, `cut to:`, `dissolve to:` and `fade out.`.

The help tree explicitly contains topics for:

- About auto-convert
- About auto-type
- About paragraph types
- About the Tab & Enter keys
- Basic editing
- Cut & Paste
- Drag & Drop
- Writing scene headers
- Writing dialogue
- Parentheticals in dialogue
- Multiple cues
- Transitions in
- Spell-check & thesaurus
- Script timing

## Trumbo behavior to preserve

The following should be treated as the implementation target unless Felipe explicitly changes it.

### Paragraph types

Core screenplay types:

- Scene Heading
- Action
- Cue/Character
- Dialogue
- Parenthetical
- Transition-In
- Transition-Out

Trumbo extensions may include SUPER/GC without changing the base behavior.

### Auto-convert

Recognition should change the semantic type of the current paragraph without destroying text or unexpectedly moving the caret.

Scene-heading auto-convert must recognize the configured `INT.` / `EXT.` forms. For Trumbo's current product rule, only `INT.` and `EXT.` should create scenes automatically.

Transition recognition must happen before cue/character inference so `CUT TO:` cannot become a character cue.

### Explorer synchronization

The compiled command `Synchronize Explorer Window to current position` and separate Header/Character/Location/Resource Explorer classes show that Explorer navigation is a first-class part of the product.

For Trumbo:

```text
screenplay document -> headings -> scenes -> Explorer
```

The Explorer should be a projection of the screenplay/project model, not an independent source of truth.

### Spell check

Sophocles provides an explicit F7 Spell Check command, a thesaurus command, a custom dictionary command, and a `CSpellErrorDlg` class. Therefore spellchecking is a real editor subsystem in Sophocles, not merely an HTML/browser attribute.

For Trumbo, browser-native spellcheck can be a temporary implementation, but if it cannot provide reliable Spanish checking the correct long-term solution is an explicit spellcheck subsystem rather than repeatedly patching `spellcheck=true`.

### Formatting and keyboard

Do not infer exact Tab/Enter transitions solely from this static binary report when the manual/user observation provides stronger evidence. Use the Sophocles manual and Felipe's live Sophocles behavior as the primary reference for exact keystroke transitions.

## Acceptance principle

A behavior is not complete because code compiles. It is complete only after manual editor validation against Sophocles behavior.
