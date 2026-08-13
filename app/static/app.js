
const state = {
  projects: [],
  project: null,
  document: null,
  documentLines: [],
  scenes: [],
  activeSceneId: null,

  // Cada escena administra su propio guardado.
  saveTimers: new Map(),
  saveRevisions: new Map(),
  savingScenes: new Set(),

  analysisTimer: null,

  activeLine: null,
  isRendering: false,
  isHydratingScenesFromDocument: false,
  isReconcilingScenes: false,
  reconcileTimer: null,
  pendingReconcile: false,
};

const LINE_TYPES = [
  "heading",
  "action",
  "character",
  "parenthetical",
  "dialogue",
  "transition",
];

const LINE_LABELS = {
  heading: "ENCABEZADO",
  action: "ACCIÓN",
  character: "PERSONAJE",
  parenthetical: "PARENTÉTICO",
  dialogue: "DIÁLOGO",
  transition: "TRANSICIÓN",
};

const TAB_FORWARD = {
  heading: "action",
  action: "character",
  character: "parenthetical",
  parenthetical: "dialogue",
  dialogue: "transition",
  transition: "heading",
};

const TAB_BACKWARD = {
  heading: "transition",
  action: "heading",
  character: "action",
  parenthetical: "character",
  dialogue: "parenthetical",
  transition: "dialogue",
};

const $ = selector => document.querySelector(selector);

const HEADING_PREFIX_REGEX =
  /^(INT\.|EXT\.)\s*/i;

const HEADING_TOKEN_ONLY_REGEX =
  /^(INT\.|EXT\.)$/i;

const HEADING_COMPLETE_REGEX =
  /^(INT\.|EXT\.)\s*.+/i;

const TRANSITION_IN_REGEX =
  /^FADE IN:$/i;

const TRANSITION_OUT_REGEX =
  /^(CUT TO:|FADE OUT:|MATCH CUT:|SMASH CUT:|JUMP CUT:|DISSOLVE TO:|WIPE TO:|CORTE A:|FUNDIDO A:|DISOLVENCIA A:)$/i;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function isHeadingPrefixText(value) {
  return HEADING_PREFIX_REGEX.test(
    String(value || "").trim()
  );
}

function isHeadingTokenOnly(value) {
  return HEADING_TOKEN_ONLY_REGEX.test(
    String(value || "").trim()
  );
}

function isCompleteHeadingText(value) {
  const text = String(value || "").trim();

  return (
    HEADING_COMPLETE_REGEX.test(text) &&
    !isHeadingTokenOnly(text)
  );
}

function isValidSceneHeadingText(value) {
  const text = String(value || "").trim();

  if (!text) {
    return false;
  }

  return isHeadingPrefixText(text);
}

function isTransitionText(value) {
  const text = String(value || "").trim();

  return (
    TRANSITION_IN_REGEX.test(text) ||
    TRANSITION_OUT_REGEX.test(text)
  );
}

function formatSeconds(total = 0) {
  const safeTotal = Number.isFinite(Number(total)) ? Number(total) : 0;
  const minutes = Math.floor(safeTotal / 60).toString().padStart(2, "0");
  const seconds = Math.floor(safeTotal % 60).toString().padStart(2, "0");

  return `${minutes}:${seconds}`;
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    const detail = await response
      .json()
      .catch(() => ({
        detail: "Error inesperado",
      }));

    throw new Error(
      detail.detail || `Error ${response.status}`
    );
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

function activeScene() {
  return (
    state.scenes.find(
      scene => scene.id === state.activeSceneId
    ) || null
  );
}

function sceneElement(sceneId) {
  return $(
    `.script-scene[data-scene-id="${sceneId}"]`
  );
}

function lineElements(sceneNode) {
  return [
    ...sceneNode.querySelectorAll(
      ":scope > .script-line"
    ),
  ];
}

function semanticStorageKey(sceneId) {
  return `trumbo-alpha-03-scene-${sceneId}`;
}

function normalizeSemanticLines(lines) {
  if (!Array.isArray(lines)) {
    return [];
  }

  return lines
    .filter(item =>
      item &&
      LINE_TYPES.includes(item.type) &&
      typeof item.text === "string"
    )
    .map(item => ({
      type: item.type,
      text: item.text,
    }));
}

function loadLegacySemanticLines(sceneId) {
  try {
    const stored = localStorage.getItem(
      semanticStorageKey(sceneId)
    );

    if (!stored) {
      return [];
    }

    return normalizeSemanticLines(
      JSON.parse(stored)
    );
  } catch (error) {
    console.warn(
      "No fue posible recuperar el formato semántico antiguo.",
      error
    );

    return [];
  }
}

function removeLegacySemanticLines(sceneId) {
  try {
    localStorage.removeItem(
      semanticStorageKey(sceneId)
    );
  } catch (error) {
    console.warn(
      "No fue posible limpiar el formato local antiguo.",
      error
    );
  }
}

 

function inferLineType(text, previousType = null) {
  const value = String(text || "").trim();

  if (!value) {
    return (
      previousType === "character" ||
      previousType === "parenthetical"
    )
      ? "dialogue"
      : "action";
  }

 if (isHeadingPrefixText(value)) {
    return "heading";
}

  if (
    value.startsWith("(") &&
    value.endsWith(")")
  ) {
    return "parenthetical";
  }

  if (isTransitionText(value)) {
    return "transition";
  }

  const looksUppercase =
    value === value.toUpperCase() &&
    /[A-ZÁÉÍÓÚÜÑ]/.test(value);

  if (
    looksUppercase &&
    value.length <= 45 &&
    !/[.!?]$/.test(value)
  ) {
    return "character";
  }

  if (
    previousType === "character" ||
    previousType === "parenthetical" ||
    previousType === "dialogue"
  ) {
    return "dialogue";
  }

  return "action";
}

function sceneToSemanticLines(scene) {
  const serverLines = normalizeSemanticLines(
    scene.semantic_lines
  );

  if (serverLines.length) {
    return serverLines;
  }

  // Recuperación temporal del formato guardado
  // por la versión anterior del editor.
  const legacyLines = loadLegacySemanticLines(
    scene.id
  );

  if (legacyLines.length) {
    scene.semantic_lines = legacyLines;
    return legacyLines;
  }

  // Compatibilidad con escenas antiguas que solo
  // tienen heading y body.
  const result = [];

  const heading =
    String(scene.heading || "").trim();

  if (heading) {
    result.push({
      type: "heading",
      text: heading,
    });
  }

  const bodyLines =
    String(scene.body || "")
      .split(/\r?\n/);

  let previousType =
    heading ? "heading" : "action";

  for (const text of bodyLines) {
    const type = inferLineType(
      text,
      previousType
    );

    result.push({
      type,
      text,
    });

    previousType = type;
  }

  if (!result.length) {
    result.push({
      type: "action",
      text: "",
    });
  }

  if (
    result.length === 1 &&
    result[0].type === "heading"
  ) {
    result.push({
      type: "action",
      text: "",
    });
  }

  scene.semantic_lines = result;

  return result;
}
function createLine(type = "action", text = "") {
  const line = document.createElement("div");

  line.className = `script-line ${type}`;
  line.dataset.type = type;
  line.contentEditable = "true";
  line.lang = "es";

  setLineSpellcheck(line);

  line.setAttribute(
    "role",
    "textbox"
  );

  line.setAttribute(
    "aria-label",
    LINE_LABELS[type] || "Línea"
  );

  line.setAttribute("lang", "es");
  line.setAttribute("autocorrect", "on");

  line.textContent = text;

  applyTransitionVariant(line);
  syncLineDelimiterState(line);

  line.addEventListener(
    "focus",
    handleLineFocus
  );

  line.addEventListener(
    "click",
    handleLineFocus
  );

  line.addEventListener(
    "keydown",
    handleLineKeydown
  );

  line.addEventListener(
    "input",
    handleLineInput
  );

  line.addEventListener(
    "blur",
    handleLineBlur
  );

  line.addEventListener(
    "paste",
    handleLinePaste
  );

  return line;
}

function createSceneNode(scene) {
  const section = document.createElement(
    "section"
  );

  section.className = "script-scene";

  section.dataset.sceneId =
    String(scene.id);

  section.dataset.sceneNumber =
    String(scene.scene_number);

  const semanticLines =
    sceneToSemanticLines(scene);

  semanticLines.forEach(item => {
    section.appendChild(
      createLine(
        item.type,
        item.text
      )
    );
  });

  ensureSceneStructure(section);

  return section;
}

function ensureSceneStructure(sceneNode) {
  let lines = lineElements(sceneNode);

  if (!lines.length) {
    sceneNode.append(
      createLine(
        "action",
        ""
      )
    );

    return;
  }

  if (lines.length === 1) {
    sceneNode.appendChild(
      createLine(
        "action",
        ""
      )
    );
  }
}

function renderScreenplay() {
  const editor = $("#screenplayEditor");

  editor.lang = "es";
  editor.spellcheck = true;
  editor.setAttribute("lang", "es");
  editor.setAttribute("spellcheck", "true");
  editor.setAttribute("autocorrect", "on");

  state.isRendering = true;
  editor.innerHTML = "";

  if (!state.scenes.length) {
    editor.append(
      createLine(
        "transition",
        "FADE IN:"
      ),
      createLine(
        "action",
        ""
      )
    );

    state.isRendering = false;
    return;
  }

  state.scenes.forEach(scene => {
    editor.appendChild(
      createSceneNode(scene)
    );
  });

  state.isRendering = false;

  setActiveScene(
    state.activeSceneId ||
      state.scenes[0]?.id,
    {
      scroll: false,
      focus: false,
    }
  );
}

function renderSceneList() {
  const container = $("#sceneList");

  if (!state.scenes.length) {
    container.innerHTML = `
      <div class="empty">
        El proyecto aún no tiene escenas.
      </div>
    `;

    return;
  }

  container.innerHTML =
    state.scenes.map(scene => `
      <div
        class="scene-card ${
          scene.id === state.activeSceneId
            ? "active"
            : ""
        }"
        data-scene-id="${scene.id}"
      >

        <div class="scene-number">
          ESCENA ${scene.scene_number}
        </div>

        <div class="scene-card-heading">
          ${
            escapeHtml(
              scene.heading ||
              "Sin encabezado"
            )
          }
        </div>

        <div class="scene-card-runtime">
          ${
            formatSeconds(
              scene.runtime_seconds
            )
          }
        </div>

      </div>
    `).join("");

  container
    .querySelectorAll(".scene-card")
    .forEach(card => {
      card.addEventListener(
        "click",
        () => {
          setActiveScene(
            Number(
              card.dataset.sceneId
            ),
            {
              scroll: true,
              focus: false,
            }
          );
        }
      );
    });
}

function setActiveScene(
  sceneId,
  options = {}
) {
  const {
    scroll = false,
    focus = false,
  } = options;

  const scene = state.scenes.find(
    item =>
      item.id === Number(sceneId)
  );

  if (!scene) {
    return;
  }

  state.activeSceneId = scene.id;

  document
    .querySelectorAll(".script-scene")
    .forEach(node => {
      node.classList.toggle(
        "active",
        Number(
          node.dataset.sceneId
        ) === scene.id
      );
    });

  document
    .querySelectorAll(".scene-card")
    .forEach(card => {
      card.classList.toggle(
        "active",
        Number(
          card.dataset.sceneId
        ) === scene.id
      );
    });

  $("#sceneIdentity").textContent =
    `ESCENA ${scene.scene_number}`;

  $("#sceneSynopsis").value =
    scene.synopsis || "";

  $("#sceneRuntime").textContent =
    formatSeconds(
      scene.runtime_seconds
    );

  renderNotes(scene);
  renderBreakdown(scene);
  scheduleSceneAnalysis(0);

  const node = sceneElement(scene.id);

  if (scroll && node) {
    node.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  if (focus && node) {
    const target =
      node.querySelector(
        ".script-line.action"
      ) ||
      node.querySelector(
        ".script-line"
      );

    focusLine(
      target,
      true
    );
  }
}
function getLineType(line) {
  return line?.dataset.type || "action";
}

function setLineSpellcheck(line) {
  if (!line) {
    return;
  }

  const type = getLineType(line);
  const enabled =
    type !== "character" &&
    type !== "heading";

  line.spellcheck = enabled;
  line.lang = "es";
  line.setAttribute(
    "spellcheck",
    String(enabled)
  );
  line.setAttribute("lang", "es");
  line.setAttribute("autocorrect", enabled ? "on" : "off");
}

function isSceneDelimiterLine(line) {
  if (!line) {
    return false;
  }

  if (getLineType(line) !== "heading") {
    return false;
  }

  return isCompleteHeadingText(
    line.textContent || ""
  );
}

function syncLineDelimiterState(line) {
  if (!line) {
    return false;
  }

  const previous =
    line.dataset.sceneDelimiter === "1";

  const current =
    isSceneDelimiterLine(line);

  line.dataset.sceneDelimiter =
    current ? "1" : "0";

  return previous !== current;
}

function applyTransitionVariant(line) {
  if (!line) {
    return;
  }

  delete line.dataset.transitionVariant;

  if (getLineType(line) !== "transition") {
    return;
  }

  const text =
    (line.textContent || "").trim();

  if (TRANSITION_IN_REGEX.test(text)) {
    line.dataset.transitionVariant = "in";
    return;
  }

  if (isTransitionText(text)) {
    line.dataset.transitionVariant = "out";
  }
}

function setLineType(
  line,
  type,
  options = {}
) {
  if (
    !line ||
    !LINE_TYPES.includes(type)
  ) {
    return;
  }

  const {
    preserveCaret = false,
    skipSceneSplit = false,
  } = options;

  const selection =
    preserveCaret
      ? window.getSelection()
      : null;

  const offset =
    preserveCaret &&
    selection?.rangeCount
      ? selection
          .getRangeAt(0)
          .startOffset
      : null;

  LINE_TYPES.forEach(item => {
    line.classList.remove(item);
  });

  line.classList.add(type);
  line.dataset.type = type;

  line.setAttribute(
    "aria-label",
    LINE_LABELS[type] || "Línea"
  );

  setLineSpellcheck(line);

  if (
    type === "character" ||
    type === "heading" ||
    type === "transition"
  ) {
    const uppercaseText =
      (line.textContent || "").toUpperCase();

    if (
      line.textContent !== uppercaseText
    ) {
      line.textContent = uppercaseText;

      if (
        preserveCaret &&
        offset !== null &&
        line.firstChild
      ) {
        const range =
          document.createRange();

        const safeOffset =
          Math.min(
            offset,
            line.firstChild
              .textContent.length
          );

        range.setStart(
          line.firstChild,
          safeOffset
        );

        range.collapse(true);

        selection.removeAllRanges();
        selection.addRange(range);
      } else {
        placeCaretAtEnd(line);
      }
    }
  }

  applyTransitionVariant(line);
  syncLineDelimiterState(line);

  const lineIsActive =
    state.activeLine === line ||
    document.activeElement === line;

  if (lineIsActive) {
    updateModeLabel(type);
  }

  if (
    type === "heading" &&
    !skipSceneSplit
  ) {
    scheduleDocumentSceneReconciliation(0);
    return;
  }

  const sceneNode =
    line.closest(".script-scene");

  if (sceneNode) {
    scheduleSceneSave(sceneNode);
  }
}

function updateModeLabel(type) {
  $("#editorModeLabel").textContent =
    LINE_LABELS[type] ||
    String(type || "").toUpperCase();
}

function focusLine(
  line,
  atEnd = true
) {
  if (!line) {
    return;
  }

  line.focus();

  if (atEnd) {
    placeCaretAtEnd(line);
  }

  handleLineFocus({
    currentTarget: line,
  });
}

function placeCaretAtEnd(element) {
  const range =
    document.createRange();

  const selection =
    window.getSelection();

  range.selectNodeContents(element);
  range.collapse(false);

  selection.removeAllRanges();
  selection.addRange(range);
}

function placeCaretAtStart(element) {
  const range =
    document.createRange();

  const selection =
    window.getSelection();

  range.selectNodeContents(element);
  range.collapse(true);

  selection.removeAllRanges();
  selection.addRange(range);
}

function selectAllInCurrentScene(line) {
  const selection =
    window.getSelection();

  if (!selection) {
    return;
  }

  const sceneNode =
    line?.closest(".script-scene");

  const lines = sceneNode
    ? lineElements(sceneNode)
    : [...document.querySelectorAll("#screenplayEditor > .script-line")];

  if (!lines.length) {
    return;
  }

  const first = lines[0];
  const last =
    lines[lines.length - 1];

  const range =
    document.createRange();

  range.setStartBefore(first);
  range.setEndAfter(last);

  selection.removeAllRanges();
  selection.addRange(range);
}

function caretIsAtStart(element) {
  const selection =
    window.getSelection();

  if (
    !selection ||
    !selection.rangeCount
  ) {
    return false;
  }

  const range =
    selection.getRangeAt(0);

  if (!range.collapsed) {
    return false;
  }

  const probe =
    range.cloneRange();

  probe.selectNodeContents(element);

  probe.setEnd(
    range.endContainer,
    range.endOffset
  );

  return probe.toString().length === 0;
}

function caretIsAtEnd(element) {
  const selection =
    window.getSelection();

  if (
    !selection ||
    !selection.rangeCount
  ) {
    return false;
  }

  const range =
    selection.getRangeAt(0);

  if (!range.collapsed) {
    return false;
  }

  const probe =
    range.cloneRange();

  probe.selectNodeContents(element);

  probe.setStart(
    range.endContainer,
    range.endOffset
  );

  return probe.toString().length === 0;
}

function insertLineAfter(
  referenceLine,
  type,
  text = ""
) {
  const line = createLine(
    type,
    text
  );

  referenceLine.after(line);

  return line;
}

function nextTypeAfterEnter(line) {
  const type = getLineType(line);
  const content =
    (line?.textContent || "")
      .trim()
      .toUpperCase();

  if (
    content === "SUPER:" ||
    content === "GC:"
  ) {
    return "action";
  }

  if (type === "heading") {
    return "action";
  }

  if (type === "character") {
    return "dialogue";
  }

  if (type === "parenthetical") {
    return "dialogue";
  }

  if (type === "dialogue") {
    return "action";
  }

  if (type === "transition") {
    return "action";
  }

  return "action";
}

function splitLineAtCaret(
  line,
  nextType
) {
  const selection =
    window.getSelection();

  if (
    !selection ||
    !selection.rangeCount
  ) {
    return insertLineAfter(
      line,
      nextType,
      ""
    );
  }

  const range =
    selection.getRangeAt(0);

  const afterRange =
    range.cloneRange();

  afterRange.selectNodeContents(line);

  afterRange.setStart(
    range.endContainer,
    range.endOffset
  );

  const tail =
    afterRange.toString();

  afterRange.deleteContents();

  return insertLineAfter(
    line,
    nextType,
    tail
  );
}

function removeCurrentLineIfEmpty(line) {
  if (!line) {
    return false;
  }

  if ((line.textContent || "").trim()) {
    return false;
  }

  const sceneNode =
    line.closest(".script-scene");

  if (!sceneNode) {
    return false;
  }

  const siblings =
    sceneNode.querySelectorAll(
      ":scope > .script-line"
    );

  if (siblings.length <= 1) {
    line.textContent = "";
    focusLine(line, true);
    return false;
  }

  const target =
    line.previousElementSibling?.classList.contains(
      "script-line"
    )
      ? line.previousElementSibling
      : line.nextElementSibling;

  if (!target) {
    return false;
  }

  line.remove();

  focusLine(target, true);
  scheduleSceneSave(sceneNode);

  return true;
}

function mergeWithPreviousLine(line) {
  const previous =
    line.previousElementSibling;

  if (
    !previous ||
    !previous.classList.contains(
      "script-line"
    )
  ) {
    return false;
  }

  const previousLength =
    (previous.textContent || "").length;

  previous.textContent =
    `${previous.textContent || ""}${line.textContent || ""}`;

  line.remove();
  previous.focus();

  const selection =
    window.getSelection();

  const range =
    document.createRange();

  const node =
    previous.firstChild ||
    previous;

  try {
    range.setStart(
      node,
      Math.min(
        previousLength,
        node.textContent?.length || 0
      )
    );
  } catch (error) {
    range.selectNodeContents(previous);
    range.collapse(false);
  }

  range.collapse(true);

  selection.removeAllRanges();
  selection.addRange(range);

  return true;
}

function autocapitalizeLineStart(line) {
  if (!line) {
    return;
  }

  const original =
    line.textContent || "";

  const updated =
    original.replace(
      /^(\s*)([a-záéíóúñü])/,
      (match, spaces, first) =>
        `${spaces}${first.toUpperCase()}`
    );

  if (updated === original) {
    return;
  }

  const selection =
    window.getSelection();

  const offset =
    selection?.rangeCount
      ? selection
          .getRangeAt(0)
          .startOffset
      : null;

  line.textContent = updated;

  if (
    offset !== null &&
    line.firstChild
  ) {
    const range =
      document.createRange();

    const safeOffset =
      Math.min(
        offset,
        line.firstChild
          .textContent.length
      );

    range.setStart(
      line.firstChild,
      safeOffset
    );

    range.collapse(true);

    selection.removeAllRanges();
    selection.addRange(range);
  }
}

function handleLineFocus(event) {
  const line =
    event.currentTarget;

  state.activeLine = line;

  document
    .querySelectorAll(
      ".script-line.selected-line"
    )
    .forEach(node => {
      node.classList.remove(
        "selected-line"
      );
    });

  line.classList.add(
    "selected-line"
  );

  updateModeLabel(
    getLineType(line)
  );

  const sceneNode =
    line.closest(".script-scene");

  if (sceneNode) {
    setActiveScene(
      Number(
        sceneNode.dataset.sceneId
      ),
      {
        scroll: false,
        focus: false,
      }
    );
  }
}

function markPendingStructuralReconcile(line) {
  if (!line) {
    return;
  }

  line.dataset.pendingStructuralReconcile =
    "1";
}

function handleLineBlur(event) {
  const line =
    event.currentTarget;

  const nextTarget =
    event.relatedTarget;

  if (
    nextTarget?.classList?.contains(
      "script-line"
    )
  ) {
    if (
      line?.dataset
        ?.pendingStructuralReconcile ===
      "1"
    ) {
      markPendingStructuralReconcile(
        nextTarget
      );

      line.dataset.pendingStructuralReconcile =
        "0";
    }

    return;
  }

  if (state.activeLine === line) {
    state.activeLine = null;

    line.classList.remove(
      "selected-line"
    );

    updateModeLabel("action");
  }

  if (
    line?.dataset
      ?.pendingStructuralReconcile !==
    "1"
  ) {
    return;
  }

  line.dataset.pendingStructuralReconcile =
    "0";

  scheduleDocumentSceneReconciliation();
}

function normalizeLineForReconciliation(
  line,
  isFirstLineInChunk = false
) {
  if (!line) {
    return;
  }

  const type = getLineType(line);
  const text =
    String(line.textContent || "").trim();

  // Evita que queden headings vacíos
  // dentro de una escena tras ediciones
  // o selecciones amplias de texto.
  if (
    type === "heading" &&
    !text &&
    !isFirstLineInChunk
  ) {
    setLineType(line, "action", {
      preserveCaret: false,
      skipSceneSplit: true,
    });
  }
}

function placeCaretAtEnd(element) {
  const selection =
    window.getSelection();

  const range =
    document.createRange();

  range.selectNodeContents(
    element
  );

  range.collapse(false);

  selection.removeAllRanges();
  selection.addRange(range);

  element.focus();
}

function handleHeadingTab(line) {
  const text =
    (line.textContent || "").trimEnd();

  // Después de INT., EXT., INT/EXT., etc.,
  // TAB agrega un espacio y deja el cursor al final.
  if (
    /^(INT\.|EXT\.)$/i.test(
      text
    )
  ) {
    line.textContent =
      `${text} `;

    placeCaretAtEnd(line);

    return;
  }

  // Evita duplicar el separador.
  if (
    text.endsWith("-")
  ) {
    line.textContent =
      `${text} `;

    placeCaretAtEnd(line);

    return;
  }

  // Entre locación, sublocación y momento del día.
  line.textContent =
    `${text} - `;

  placeCaretAtEnd(line);
}

function allDocumentLines(editor) {
  return [
    ...editor.querySelectorAll(
      ".script-line"
    ),
  ];
}

function deriveSceneChunksFromDocument(lines) {
  const chunks = [];
  const prefaceLines = [];
  let currentChunk = null;

  lines.forEach(line => {
    const text =
      String(line.textContent || "").trim();

    if (isCompleteHeadingText(text)) {
      setLineType(line, "heading", {
        preserveCaret: false,
        skipSceneSplit: true,
      });

      if (currentChunk) {
        chunks.push(currentChunk);
      }

      currentChunk = {
        heading: text,
        lines: [line],
      };

      return;
    }

    if (!currentChunk) {
      prefaceLines.push(line);
      return;
    }

    currentChunk.lines.push(line);
  });

  if (currentChunk) {
    chunks.push(currentChunk);
  }

  return {
    prefaceLines,
    chunks,
  };
}

function renderNoActiveScene() {
  $("#sceneIdentity")
    .textContent =
      "SIN ESCENA";

  $("#sceneSynopsis")
    .value = "";

  $("#sceneRuntime")
    .textContent =
      "00:00";

  renderNotes(null);
  renderBreakdown(null);

  $("#scriptAnalysis")
    .innerHTML = `
      <div class="empty">
        No hay una escena activa.
      </div>
    `;

  const spellList =
    $("#spellcheckList");

  if (spellList) {
    spellList.innerHTML = `
      <div class="empty">
        No hay una escena activa.
      </div>
    `;
  }
}

async function syncSceneRecordsToChunkCount(chunkCount) {
  if (!state.project) {
    return;
  }

  while (state.scenes.length < chunkCount) {
    const created =
      await request(
        `/api/projects/${state.project.id}/scenes`,
        {
          method: "POST",
          body: JSON.stringify({}),
        }
      );

    created.notes =
      created.notes || [];

    created.breakdown_items =
      created.breakdown_items || [];

    state.scenes.push(created);
  }

  while (state.scenes.length > chunkCount) {
    const removed = state.scenes.pop();

    try {
      await request(
        `/api/scenes/${removed.id}`,
        {
          method: "DELETE",
        }
      );
    } catch (error) {
      console.error(
        "No fue posible eliminar escena durante reconciliación.",
        error
      );
    }
  }
}

async function reconcileScenesFromDocument() {
  if (!state.project) {
    return false;
  }

  const editor =
    $("#screenplayEditor");

  if (!editor) {
    return false;
  }

  if (state.isReconcilingScenes) {
    state.pendingReconcile = true;
    return false;
  }

  state.isReconcilingScenes = true;

  try {
    const sourceLines =
      allDocumentLines(editor);

    const {
      prefaceLines,
      chunks,
    } = deriveSceneChunksFromDocument(
      sourceLines
    );

    setSaveState(
      "Sincronizando escenas…",
      "saving"
    );

    await syncSceneRecordsToChunkCount(
      chunks.length
    );

    renumberScenesLocally();

    const sceneNodes = [];

    chunks.forEach(
      (chunk, index) => {
        const scene =
          state.scenes[index];

        if (!scene) {
          return;
        }

        const section =
          document.createElement(
            "section"
          );

        section.className =
          "script-scene";

        section.dataset.sceneId =
          String(scene.id);

        section.dataset.sceneNumber =
          String(
            scene.scene_number
          );

        chunk.lines.forEach((line, lineIndex) => {
          normalizeLineForReconciliation(
            line,
            lineIndex === 0
          );

          section.appendChild(line);
        });

        ensureSceneStructure(section);

        scene.heading =
          chunk.heading;

        sceneNodes.push(section);
      }
    );

    editor.innerHTML = "";

    prefaceLines.forEach(line => {
      editor.appendChild(line);
    });

    sceneNodes.forEach(node => {
      editor.appendChild(node);
    });

    if (state.scenes.length) {
      const stillActive =
        state.scenes.some(
          scene =>
            scene.id ===
            state.activeSceneId
        );

      if (!stillActive) {
        state.activeSceneId =
          state.scenes[0].id;
      }
    } else {
      state.activeSceneId = null;
    }

    renderSceneList();

    if (state.activeSceneId) {
      setActiveScene(
        state.activeSceneId,
        {
          scroll: false,
          focus: false,
        }
      );
    } else {
      renderNoActiveScene();
    }

    for (const sceneNode of sceneNodes) {
      await saveSceneNode(sceneNode);
    }

    setSaveState(
      "Guardado",
      "saved"
    );

    return true;
  } catch (error) {
    console.error(error);

    setSaveState(
      "Error de sincronización",
      "error"
    );

    return false;
  } finally {
    state.isReconcilingScenes = false;

    if (state.pendingReconcile) {
      state.pendingReconcile = false;
      scheduleDocumentSceneReconciliation(120);
    }
  }
}

function scheduleDocumentSceneReconciliation(
  delay = 180
) {
  if (state.reconcileTimer) {
    clearTimeout(
      state.reconcileTimer
    );
  }

  state.reconcileTimer =
    setTimeout(() => {
      state.reconcileTimer = null;
      reconcileScenesFromDocument();
    }, delay);
}

async function materializeScenesFromDraftDocument() {
  return reconcileScenesFromDocument();
}

function handleLineKeydown(event) {
  const line =
    event.currentTarget;

  const type =
    getLineType(line);

  if (
    (event.ctrlKey || event.metaKey) &&
    !event.shiftKey &&
    !event.altKey &&
    event.key.toLowerCase() === "a"
  ) {
    event.preventDefault();
    selectAllInCurrentScene(line);
    return;
  }

 if (event.key === "Tab") {
  event.preventDefault();

  if (
    type === "action" &&
    !event.shiftKey &&
    (line.textContent || "").trim()
  ) {
    const cueLine =
      insertLineAfter(
        line,
        "character",
        ""
      );

    focusLine(
      cueLine,
      true
    );

    scheduleSceneSave(
      line.closest(".script-scene")
    );

    return;
  }

  // En un encabezado, TAB construye la ruta:
  // INT. LOCACIÓN - SUBLOCACIÓN - DÍA
  if (
    type === "heading" &&
    !event.shiftKey
  ) {
    handleHeadingTab(line);

    scheduleSceneSave(
      line.closest(".script-scene")
    );

    return;
  }

  const nextType =
    event.shiftKey
      ? TAB_BACKWARD[type]
      : TAB_FORWARD[type];

  setLineType(
    line,
    nextType || "action"
  );

  focusLine(
    line,
    true
  );

  return;
}

  if (event.key === "Enter") {
    event.preventDefault();

    if (event.shiftKey) {
      document.execCommand(
        "insertLineBreak"
      );

      return;
    }

    const nextType =
      nextTypeAfterEnter(line);

    const nextLine =
      splitLineAtCaret(
        line,
        nextType
      );

    if (nextType === "heading") {
      nextLine.textContent = "INT. ";
    }

    focusLine(
      nextLine,
      true
    );

    scheduleSceneSave(
      nextLine.closest(
        ".script-scene"
      )
    );

    markPendingStructuralReconcile(
      nextLine
    );

    return;
  }

  if (
    event.key === "Delete" ||
    event.key === "Del"
  ) {
    const sceneNode =
      line.closest(".script-scene");

    if (removeCurrentLineIfEmpty(line)) {
      event.preventDefault();

      updateSceneHeadingFromDom(
        sceneNode
      );

      return;
    }

    if ((line.textContent || "").trim()) {
      return;
    }
  }

  if (
    event.key === "Backspace" &&
    caretIsAtStart(line) &&
    !(
      line.closest(
        ".script-scene"
      )?.firstElementChild === line
    )
  ) {
    event.preventDefault();

    const sceneNode =
      line.closest(
        ".script-scene"
      );

    if (
      mergeWithPreviousLine(line)
    ) {
      updateSceneHeadingFromDom(
        sceneNode
      );

      scheduleSceneSave(
        sceneNode
      );
    }

    return;
  }

  if (
    event.key === "ArrowUp" &&
    caretIsAtStart(line)
  ) {
    const previous =
      line.previousElementSibling;

    if (
      previous &&
      previous.classList.contains(
        "script-line"
      )
    ) {
      event.preventDefault();

      focusLine(
        previous,
        true
      );
    }

    return;
  }

  if (
    event.key === "ArrowDown" &&
    caretIsAtEnd(line)
  ) {
    const next =
      line.nextElementSibling;

    if (
      next &&
      next.classList.contains(
        "script-line"
      )
    ) {
      event.preventDefault();

      focusLine(
        next,
        false
      );

      placeCaretAtStart(next);
    }
  }
}

function handleLineInput(event) {
  if (state.isRendering) {
    return;
  }

  const line =
    event.currentTarget;

  const type =
    getLineType(line);

  if (
    type === "action" ||
    type === "dialogue" ||
    type === "parenthetical"
  ) {
    autocapitalizeLineStart(line);
  }

  if (
    type === "character" ||
    type === "heading" ||
    type === "transition"
  ) {
    const selection =
      window.getSelection();

    const offset =
      selection?.rangeCount
        ? selection
            .getRangeAt(0)
            .startOffset
        : null;

    const uppercaseText =
      (line.textContent || "")
        .toUpperCase();

    if (
      line.textContent !==
      uppercaseText
    ) {
      line.textContent =
        uppercaseText;

      if (
        offset !== null &&
        line.firstChild
      ) {
        const range =
          document.createRange();

        const safeOffset =
          Math.min(
            offset,
            line.firstChild
              .textContent.length
          );

        range.setStart(
          line.firstChild,
          safeOffset
        );

        range.collapse(true);

        selection.removeAllRanges();
        selection.addRange(range);
      }
    }
  }

  const lineText =
    (line.textContent || "")
      .trim();

  if (
    type !== "heading" &&
    isHeadingPrefixText(lineText)
  ) {
    setLineType(
      line,
      "heading",
      {
        preserveCaret: true,
        // Durante escritura no reconciliamos
        // estructura de escenas en caliente.
        skipSceneSplit: true,
      }
    );
  }

  if (
    getLineType(line) !== "transition" &&
    isTransitionText(lineText)
  ) {
    setLineType(
      line,
      "transition",
      {
        preserveCaret: true,
      }
    );
  }

  const sceneNode =
    line.closest(".script-scene");

  updateSceneHeadingFromDom(
    sceneNode
  );

  scheduleSceneSave(
    sceneNode
  );

  const delimiterChanged =
    syncLineDelimiterState(line);

  if (delimiterChanged) {
    // Se difiere a blur para no destruir
    // el nodo contenteditable activo.
    markPendingStructuralReconcile(
      line
    );
  }
}
function handleLinePaste(event) {
  event.preventDefault();

  const text =
    event.clipboardData
      ?.getData("text/plain")
      ?.replace(/\r/g, "");

  if (text == null) {
    return;
  }

  const line =
    event.currentTarget;

  const parts =
    text.split("\n");

  if (parts.length === 1) {
    document.execCommand(
      "insertText",
      false,
      parts[0]
    );

    scheduleDocumentSceneReconciliation();

    return;
  }

  document.execCommand(
    "insertText",
    false,
    parts.shift()
  );

  let reference = line;

  let previousType =
    getLineType(line);

  parts.forEach(part => {
    const type =
      inferLineType(
        part,
        previousType
      );

    const next =
      insertLineAfter(
        reference,
        type,
        part
      );

    reference = next;
    previousType = type;

  });

  focusLine(
    reference,
    true
  );

  scheduleSceneSave(
    reference.closest(
      ".script-scene"
    )
  );

  scheduleDocumentSceneReconciliation();
}

function updateSceneHeadingFromDom(
  sceneNode
) {
  if (!sceneNode) {
    return;
  }

  const sceneId =
    Number(
      sceneNode.dataset.sceneId
    );

  const scene =
    state.scenes.find(
      item =>
        item.id === sceneId
    );

  const headingLine =
    sceneNode.querySelector(
      ":scope > .script-line.heading"
    );

  if (!scene) {
    return;
  }

  scene.heading =
    (
      headingLine?.textContent ||
      ""
    ).trim();

  renderSceneList();
}

function maybeCollapseSceneWithoutHeading(sceneNode) {
  scheduleDocumentSceneReconciliation(0);
  return false;
}

async function collapseLeadingHeadinglessScene() {
  return reconcileScenesFromDocument();
}

async function splitSceneAtHeading(
  line,
  options = {}
) {
  scheduleDocumentSceneReconciliation(0);
}

function renumberScenesLocally() {
  state.scenes.forEach(
    (scene, index) => {
      scene.scene_number =
        index + 1;

      const node =
        sceneElement(scene.id);

      if (node) {
        node.dataset.sceneNumber =
          String(
            scene.scene_number
          );
      }
    }
  );
}
function serializeSceneNode(sceneNode) {
  const lines = lineElements(sceneNode);

  const semanticLines = lines.map(line => ({
    type: getLineType(line),
    text: line.textContent || "",
  }));

  const headingLine =
    lines.find(
      line => getLineType(line) === "heading"
    );

  const heading =
    headingLine
      ? (headingLine.textContent || "")
          .trim()
      : "";

  const bodyLines = headingLine
    ? lines
        .filter(line => line !== headingLine)
        .map(line => line.textContent || "")
    : lines.map(
        line => line.textContent || ""
      );

  return {
    heading,
    body: bodyLines.join("\n"),
    semantic_lines: semanticLines,
  };
}

function currentSceneRevision(sceneId) {
  return state.saveRevisions.get(sceneId) || 0;
}

function sceneHasPendingSave(sceneId) {
  return (
    state.saveTimers.has(sceneId) ||
    state.savingScenes.has(sceneId)
  );
}

function scheduleSceneSave(sceneNode) {
  if (!sceneNode) {
    return;
  }

  const sceneId =
    Number(sceneNode.dataset.sceneId);

  if (!sceneId) {
    return;
  }

  const previousTimer =
    state.saveTimers.get(sceneId);

  if (previousTimer) {
    clearTimeout(previousTimer);
  }

  const revision =
    currentSceneRevision(sceneId) + 1;

  state.saveRevisions.set(
    sceneId,
    revision
  );

  if (sceneId === state.activeSceneId) {
    setSaveState(
      "Editando…",
      "editing"
    );
  }

  const timer = setTimeout(() => {
    state.saveTimers.delete(sceneId);

    saveSceneById(
      sceneId,
      revision
    );
  }, 650);

  state.saveTimers.set(
    sceneId,
    timer
  );

  if (sceneId === state.activeSceneId) {
    scheduleSceneAnalysis(850);
  }
}

async function saveSceneById(
  sceneId,
  revision = currentSceneRevision(sceneId)
) {
  const node = sceneElement(sceneId);

  if (!node) {
    return;
  }

  await saveSceneNode(
    node,
    revision
  );
}

async function saveSceneNode(
  sceneNode,
  revision = null
) {
  if (!sceneNode) {
    return;
  }

  const sceneId =
    Number(sceneNode.dataset.sceneId);

  const scene = state.scenes.find(
    item => item.id === sceneId
  );

  if (!scene) {
    return;
  }

  const saveRevision =
    revision ??
    currentSceneRevision(sceneId);

  const serialized =
    serializeSceneNode(sceneNode);

  const synopsis =
    sceneId === state.activeSceneId
      ? $("#sceneSynopsis").value
      : scene.synopsis || "";

  state.savingScenes.add(sceneId);

  if (sceneId === state.activeSceneId) {
    setSaveState(
      "Guardando…",
      "saving"
    );
  }

  try {
    const updated = await request(
      `/api/scenes/${sceneId}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          heading: serialized.heading,
          body: serialized.body,
          semantic_lines:
            serialized.semantic_lines,
          synopsis,
        }),
      }
    );

    Object.assign(
      scene,
      updated
    );

    scene.semantic_lines =
      normalizeSemanticLines(
        updated.semantic_lines
      );

    removeLegacySemanticLines(
      sceneId
    );

    const isLatestRevision =
      saveRevision ===
      currentSceneRevision(sceneId);

    if (
      sceneId === state.activeSceneId &&
      isLatestRevision
    ) {
      $("#sceneRuntime").textContent =
        formatSeconds(
          scene.runtime_seconds
        );

      setSaveState(
        "Guardado",
        "saved"
      );
    }

    renderSceneList();
    await updateProjectRuntime();
  } catch (error) {
    console.error(
      `No fue posible guardar la escena ${sceneId}.`,
      error
    );

    const isLatestRevision =
      saveRevision ===
      currentSceneRevision(sceneId);

    if (
      sceneId === state.activeSceneId &&
      isLatestRevision
    ) {
      setSaveState(
        "Error al guardar",
        "error"
      );
    }
  } finally {
    state.savingScenes.delete(sceneId);

    const isLatestRevision =
      saveRevision ===
      currentSceneRevision(sceneId);

    if (
      sceneId === state.activeSceneId &&
      isLatestRevision
    ) {
      scheduleSceneAnalysis(120);
    }
  }
}

function scheduleSynopsisSave() {
  const scene =
    activeScene();

  const node =
    scene
      ? sceneElement(scene.id)
      : null;

  if (node) {
    scheduleSceneSave(node);
  }
}

async function updateProjectRuntime() {
  if (!state.project) {
    return;
  }

  try {
    const runtime =
      await request(
        `/api/projects/${state.project.id}/runtime`
      );

    $("#projectRuntime")
      .textContent =
        runtime.formatted ||
        formatSeconds(
          runtime.runtime_seconds ||
          0
        );
  } catch (error) {
    console.error(
      "No fue posible actualizar la duración.",
      error
    );
  }
}

function scheduleSceneAnalysis(
  delay = 500
) {
  clearTimeout(
    state.analysisTimer
  );

  state.analysisTimer =
    setTimeout(
      analyzeActiveScene,
      delay
    );
}

async function analyzeActiveScene() {
  const scene = activeScene();

  if (!scene) {
    return;
  }

  if (sceneHasPendingSave(scene.id)) {
    clearTimeout(
      state.analysisTimer
    );

    state.analysisTimer = setTimeout(
      analyzeActiveScene,
      500
    );

    return;
  }

  try {
    const analysis = await request(
      `/api/scenes/${scene.id}/analysis`
    );

    // La respuesta podría llegar después de que
    // el usuario cambió a otra escena.
    if (
      scene.id !== state.activeSceneId
    ) {
      return;
    }

    renderScriptAnalysis(
      analysis
    );
  } catch (error) {
    if (
      scene.id === state.activeSceneId
    ) {
      $("#scriptAnalysis").innerHTML =
        `<div class="empty">No fue posible analizar la escena.</div>`;
    }

    console.error(error);
  }
}

function renderScriptAnalysis(
  analysis
) {
  const counts =
    analysis?.counts || {};

  const chips =
    Object
      .entries({
        heading: "Encabezados",
        action: "Acción",
        character: "Personajes",
        dialogue: "Diálogos",
        parenthetical: "Parentéticos",
        transition: "Transiciones",
      })
      .map(
        ([key, label]) => `
          <div class="analysis-chip">
            <span>
              ${escapeHtml(label)}
            </span>

            <strong>
              ${escapeHtml(counts[key] || 0)}
            </strong>
          </div>
        `
      )
      .join("");

  const characters =
    analysis?.characters?.length
      ? `
        <div class="analysis-section">
          <div class="analysis-section-title">
            Personajes
          </div>

          <ul class="analysis-list">
            ${analysis.characters
              .map(
                character => `
                  <li>
                    ${escapeHtml(character)}
                  </li>
                `
              )
              .join("")}
          </ul>
        </div>
      `
      : `
        <div class="analysis-section">
          <div class="analysis-section-title">
            Personajes
          </div>

          <div class="analysis-empty">
            Aún no se detectan personajes.
          </div>
        </div>
      `;

  const events =
    analysis?.events?.length
      ? `
        <div class="analysis-section">
          <div class="analysis-section-title">
            Eventos
          </div>

          <ul class="analysis-list">
            ${analysis.events
              .map(
                event => `
                  <li>
                    <strong>
                      ${escapeHtml(event.title || "Evento")}
                    </strong>
                  </li>
                `
              )
              .join("")}
          </ul>
        </div>
      `
      : `
        <div class="analysis-section">
          <div class="analysis-section-title">
            Eventos
          </div>

          <div class="analysis-empty">
            Aún no se detectan eventos.
          </div>
        </div>
      `;

  const productionElements =
    analysis?.production_elements?.length
      ? `
        <div class="analysis-section">
          <div class="analysis-section-title">
            Elementos de producción
          </div>

          ${Object.entries(
            analysis.production_elements.reduce(
              (groups, element) => {
                const key = element.element_type || "unknown";
                if (!groups[key]) {
                  groups[key] = [];
                }
                groups[key].push(element);
                return groups;
              },
              {}
            )
          )
            .map(
              ([group, items]) => `
                <div class="analysis-group">
                  <div class="analysis-group-title">
                    ${escapeHtml(group)}
                  </div>

                  <ul class="analysis-list">
                    ${items
                      .map(
                        item => `
                          <li>
                            ${escapeHtml(item.name || "Elemento")}
                          </li>
                        `
                      )
                      .join("")}
                  </ul>
                </div>
              `
            )
            .join("")}
        </div>
      `
      : `
        <div class="analysis-section">
          <div class="analysis-section-title">
            Elementos de producción
          </div>

          <div class="analysis-empty">
            Aún no se detectan elementos de producción.
          </div>
        </div>
      `;

  $("#scriptAnalysis")
    .innerHTML = `
      <div class="analysis-grid">
        ${chips}
      </div>

      <div class="analysis-stack">
        ${characters}
        ${events}
        ${productionElements}
      </div>
    `;
}

function renderNotes(scene) {
  const container =
    $("#notesList");

  if (
    !scene?.notes?.length
  ) {
    container.innerHTML = `
      <div class="empty">
        No hay notas.
      </div>
    `;

    return;
  }

  container.innerHTML =
    scene.notes
      .map(
        note => `
          <div class="item">
            <div class="item-meta">
              ${
                escapeHtml(
                  note.category ||
                  "general"
                )
              }
            </div>

            <div>
              ${
                escapeHtml(
                  note.body
                )
              }
            </div>
          </div>
        `
      )
      .join("");
}

function renderBreakdown(scene) {
  const container =
    $("#breakdownList");

  const categoryFilter =
    $("#breakdownFilterCategory")
      ?.value || "all";

  const stateFilter =
    $("#breakdownFilterState")
      ?.value || "all";

  const items =
    scene?.breakdown_items?.filter(item => {
      const byCategory =
        categoryFilter === "all" ||
        item.category === categoryFilter;

      const byState =
        stateFilter === "all" ||
        item.state === stateFilter;

      return byCategory && byState;
    }) || [];

  if (
    !items.length
  ) {
    container.innerHTML = `
      <div class="empty">
        No hay elementos para el filtro actual.
      </div>
    `;

    return;
  }

  container.innerHTML =
    items
      .map(
        item => `
          <div class="item">
            <div class="item-meta">
              ${
                escapeHtml(
                  item.category
                )
              }
              ·
              ${
                escapeHtml(
                  item.state
                )
              }
            </div>

            <div>
              ${
                escapeHtml(
                  item.name
                )
              }
            </div>

            <div class="inline-form">
              <button
                type="button"
                class="secondary"
                data-breakdown-id="${item.id}"
                data-breakdown-state="confirmed"
              >
                Confirmar
              </button>

              <button
                type="button"
                class="secondary"
                data-breakdown-id="${item.id}"
                data-breakdown-state="rejected"
              >
                Rechazar
              </button>
            </div>
          </div>
        `
      )
      .join("");
}

function renderSpellingReview(
  payload,
  errorMessage = ""
) {
  const container =
    $("#spellcheckList");

  if (!container) {
    return;
  }

  if (errorMessage) {
    container.innerHTML = `
      <div class="empty">
        ${escapeHtml(errorMessage)}
      </div>
    `;
    return;
  }

  const misspellings =
    payload?.misspellings || [];

  if (!misspellings.length) {
    container.innerHTML = `
      <div class="empty">
        No se detectaron palabras dudosas.
      </div>
    `;
    return;
  }

  container.innerHTML = misspellings
    .map(item => `
      <div class="item">
        <div class="item-meta">
          ${escapeHtml(item.word)} · ${escapeHtml(item.count)}
        </div>
        <div>
          Sugerencias: ${escapeHtml((item.suggestions || []).join(", ") || "(sin sugerencias)")}
        </div>
      </div>
    `)
    .join("");
}

async function reviewSpelling() {
  const scene =
    activeScene();

  if (!scene) {
    renderSpellingReview(
      null,
      "No hay escena activa para revisar."
    );
    return;
  }

  try {
    const payload = await request(
      `/api/scenes/${scene.id}/spelling`
    );

    renderSpellingReview(payload);
  } catch (error) {
    console.error(error);
    renderSpellingReview(
      null,
      "No fue posible ejecutar la revisión ortográfica."
    );
  }
}

function exportProjectPdf() {
  if (!state.project) {
    return;
  }

  window.open(
    `/api/projects/${state.project.id}/export/pdf`,
    "_blank"
  );
}

async function updateBreakdownItemState(
  itemId,
  nextState
) {
  const scene =
    activeScene();

  if (!scene) {
    return;
  }

  try {
    const updated = await request(
      `/api/breakdown/${itemId}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          state: nextState,
        }),
      }
    );

    scene.breakdown_items =
      (scene.breakdown_items || []).map(item =>
        item.id === updated.id
          ? {
              ...item,
              ...updated,
            }
          : item
      );

    renderBreakdown(scene);
  } catch (error) {
    console.error(error);

    alert(
      "No fue posible actualizar el estado del elemento."
    );
  }
}

function proposeSynopsis() {
  const scene =
    activeScene();

  if (!scene) {
    return;
  }

  const node =
    sceneElement(
      scene.id
    );

  if (!node) {
    return;
  }

  const {
    body,
  } = serializeSceneNode(
    node
  );

  const normalized =
    body
      .replace(
        /\n+/g,
        " "
      )
      .replace(
        /\s+/g,
        " "
      )
      .trim();

  if (!normalized) {
    return;
  }

  const firstSentence =
    normalized
      .match(
        /^(.{1,220}?[.!?])(?:\s|$)/
      )?.[1] ||
    normalized.slice(
      0,
      180
    );

  $("#sceneSynopsis")
    .value =
      firstSentence;

  scheduleSynopsisSave();
}

async function addNote() {
  const scene =
    activeScene();

  const body =
    $("#noteInput")
      .value
      .trim();

  if (
    !scene ||
    !body
  ) {
    return;
  }

  try {
    const note =
      await request(
        `/api/scenes/${scene.id}/notes`,
        {
          method: "POST",
          body: JSON.stringify({
            body,
            category:
              "general",
          }),
        }
      );

    scene.notes =
      scene.notes || [];

    scene.notes.unshift(
      note
    );

    $("#noteInput")
      .value = "";

    renderNotes(scene);
  } catch (error) {
    console.error(error);

    alert(
      "No fue posible agregar la nota."
    );
  }
}

async function addBreakdownItem() {
  const scene =
    activeScene();

  const name =
    $("#breakdownName")
      .value
      .trim();

  const category =
    $("#breakdownCategory")
      .value;

  const stateValue =
    $("#breakdownState")
      ?.value || "confirmed";

  if (
    !scene ||
    !name
  ) {
    return;
  }

  try {
    const item =
      await request(
        `/api/scenes/${scene.id}/breakdown`,
        {
          method: "POST",
          body: JSON.stringify({
            category,
            name,
            source:
              "manual",
            state:
              stateValue,
          }),
        }
      );

    scene.breakdown_items =
      scene.breakdown_items ||
      [];

    scene
      .breakdown_items
      .push(item);

    $("#breakdownName")
      .value = "";

    renderBreakdown(scene);

    scheduleSceneAnalysis(
      0
    );
  } catch (error) {
    console.error(error);

    alert(
      "No fue posible agregar el elemento."
    );
  }
}
async function createProject() {
  const title =
    window.prompt(
      "Título del proyecto"
    );

  if (!title?.trim()) {
    return;
  }

  try {
    const project =
      await request(
        "/api/projects",
        {
          method: "POST",
          body: JSON.stringify({
            title:
              title.trim(),

            format:
              "feature",
          }),
        }
      );

    await loadProjects(
      project.id
    );
  } catch (error) {
    console.error(error);

    alert(
      "No fue posible crear el proyecto."
    );
  }
}

async function createScene() {
  if (!state.project) {
    return;
  }

  try {
    const scene =
      await request(
        `/api/projects/${state.project.id}/scenes`,
        {
          method: "POST",
          body: JSON.stringify({}),
        }
      );

    scene.notes =
      scene.notes || [];

    scene.breakdown_items =
      scene.breakdown_items || [];

    state.scenes.push(
      scene
    );

    renumberScenesLocally();

    const node =
      createSceneNode(
        scene
      );

    $("#screenplayEditor")
      .appendChild(node);

    state.activeSceneId =
      scene.id;

    renderSceneList();

    setActiveScene(
      scene.id,
      {
        scroll: true,
        focus: true,
      }
    );

    const focusTarget =
      node.querySelector(
        ".script-line.transition"
      ) ||
      node.querySelector(
        ".script-line.heading"
      ) ||
      node.querySelector(
        ".script-line"
      );

    if (focusTarget) {
      focusLine(
        focusTarget,
        true
      );
    }
  } catch (error) {
    console.error(error);

    alert(
      "No fue posible crear la escena."
    );
  }
}

async function loadProjects(
  preferredProjectId = null
) {
  state.projects =
    await request(
      "/api/projects"
    );

  $("#projectSelect")
    .innerHTML =
      state.projects
        .map(
          project => `
            <option value="${project.id}">
              ${
                escapeHtml(
                  project.title
                )
              }
            </option>
          `
        )
        .join("");

  const projectId =
    preferredProjectId ||
    state.projects[0]?.id;

  if (projectId) {
    await loadProject(
      projectId
    );

    return;
  }

  state.project = null;
  state.scenes = [];
  state.activeSceneId = null;

  $("#projectTitle")
    .value = "";

  renderSceneList();
  renderScreenplay();
}

async function loadProject(
  projectId
) {
  let loadedFromDocument = false;
  let mustUseLegacy = false;

  try {
    const response = await fetch(
      `/api/projects/${projectId}/document`,
      {
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      if (response.status === 404) {
        mustUseLegacy = true;
      } else {
        const detail = await response
          .json()
          .catch(() => ({
            detail: "Error inesperado",
          }));

        throw new Error(
          detail.detail ||
          `Error ${response.status}`
        );
      }
    } else {
      const documentResponse =
        await response.json();

      const derivedScenes =
        documentResponse.derived_scenes || [];

      const hasUnsafeDerivedScenes =
        derivedScenes.some(
          scene =>
            scene?.id == null ||
            scene?.structural_conflict === true
        );

      if (hasUnsafeDerivedScenes) {
        mustUseLegacy = true;
      } else {
        state.project =
          documentResponse.project;

        state.document =
          documentResponse.document;

        state.documentLines =
          documentResponse.lines || [];

        state.scenes =
          derivedScenes;

        loadedFromDocument = true;
      }
    }
  } catch (error) {
    if (!mustUseLegacy) {
      throw error;
    }
  }

  if (!loadedFromDocument) {
    const legacy =
      await request(
        `/api/projects/${projectId}`
      );

    state.project =
      legacy.project;

    state.scenes =
      legacy.scenes || [];

    state.document = null;
    state.documentLines = [];
  }

  state.activeSceneId =
    state.scenes[0]?.id ??
    null;

  $("#projectSelect")
    .value =
      String(projectId);

  $("#projectTitle")
    .value =
      state.project.title ||
      "";

  renderSceneList();
  renderScreenplay();

  if (state.activeSceneId) {
    setActiveScene(
      state.activeSceneId,
      {
        scroll: false,
        focus: false,
      }
    );
  } else {
    renderNoActiveScene();
  }

  await collapseLeadingHeadinglessScene();

  await updateProjectRuntime();
}

function setSaveState(
  text,
  stateName = ""
) {
  const indicator =
    $("#saveState");

  indicator.textContent =
    text;

  indicator.dataset.state =
    stateName;
}

function setupTabs() {
  document
    .querySelectorAll(".tab")
    .forEach(tab => {
      tab.addEventListener(
        "click",
        () => {
          document
            .querySelectorAll(
              ".tab"
            )
            .forEach(item => {
              item.classList.remove(
                "active"
              );
            });

          document
            .querySelectorAll(
              ".panel"
            )
            .forEach(panel => {
              panel.classList.remove(
                "active"
              );
            });

          tab.classList.add(
            "active"
          );

          const panel =
            $(
              `#panel-${tab.dataset.tab}`
            );

          if (panel) {
            panel.classList.add(
              "active"
            );
          }
        }
      );
    });
}

function toggleInspector() {
  const collapsed =
    document.body.classList.toggle(
      "inspector-collapsed"
    );

  const button =
    $("#toggleInspectorButton");

  if (!button) {
    return;
  }

  button.textContent =
    collapsed
      ? "Inspector ▸"
      : "Inspector ◂";

  button.setAttribute(
    "aria-pressed",
    String(collapsed)
  );
}

function setupEvents() {
  $("#projectSelect")
    .addEventListener(
      "change",
      event => {
        loadProject(
          event.target.value
        ).catch(error => {
          console.error(error);

          alert(
            "No fue posible cargar el proyecto."
          );
        });
      }
    );

  $("#newProjectButton")
    .addEventListener(
      "click",
      createProject
    );

  $("#newSceneButton")
    .addEventListener(
      "click",
      createScene
    );

  $("#sceneSynopsis")
    .addEventListener(
      "input",
      scheduleSynopsisSave
    );

  $("#suggestSynopsisButton")
    .addEventListener(
      "click",
      proposeSynopsis
    );

  $("#addNoteButton")
    .addEventListener(
      "click",
      addNote
    );

  $("#addBreakdownButton")
    .addEventListener(
      "click",
      addBreakdownItem
    );

  $("#exportPdfButton")
    .addEventListener(
      "click",
      exportProjectPdf
    );

  $("#spellcheckButton")
    .addEventListener(
      "click",
      reviewSpelling
    );

  $("#breakdownFilterCategory")
    .addEventListener(
      "change",
      () => {
        renderBreakdown(activeScene());
      }
    );

  $("#breakdownFilterState")
    .addEventListener(
      "change",
      () => {
        renderBreakdown(activeScene());
      }
    );

  $("#breakdownList")
    .addEventListener(
      "click",
      event => {
        const target =
          event.target.closest(
            "[data-breakdown-id][data-breakdown-state]"
          );

        if (!target) {
          return;
        }

        const itemId = Number(
          target.dataset.breakdownId
        );

        const nextState =
          target.dataset.breakdownState;

        if (!itemId || !nextState) {
          return;
        }

        updateBreakdownItemState(
          itemId,
          nextState
        );
      }
    );

  $("#noteInput")
    .addEventListener(
      "keydown",
      event => {
        if (
          event.key ===
          "Enter"
        ) {
          event.preventDefault();
          addNote();
        }
      }
    );

  $("#breakdownName")
    .addEventListener(
      "keydown",
      event => {
        if (
          event.key ===
          "Enter"
        ) {
          event.preventDefault();
          addBreakdownItem();
        }
      }
    );

  $("#projectTitle")
    .addEventListener(
      "change",
      async event => {
        if (!state.project) {
          return;
        }

        const title =
          event.target.value
            .trim();

        if (!title) {
          event.target.value =
            state.project.title;

          return;
        }

        try {
          const updated =
            await request(
              `/api/projects/${state.project.id}`,
              {
                method:
                  "PATCH",

                body:
                  JSON.stringify({
                    title,
                  }),
              }
            );

          state.project = {
            ...state.project,
            ...updated,
          };

          await loadProjects(
            state.project.id
          );
        } catch (error) {
          console.error(error);

          alert(
            "No fue posible actualizar el título del proyecto."
          );
        }
      }
    );

  const inspectorButton =
    $("#toggleInspectorButton");

  if (inspectorButton) {
    inspectorButton.addEventListener(
      "click",
      toggleInspector
    );
  }

  window.addEventListener(
  "beforeunload",
  event => {
    const hasPendingChanges =
      state.saveTimers.size > 0 ||
      state.savingScenes.size > 0;

    if (!hasPendingChanges) {
      return;
    }

    event.preventDefault();
    event.returnValue = "";
  }
);
}

setupTabs();
setupEvents();

loadProjects()
  .catch(error => {
    console.error(error);

    alert(
      "No fue posible iniciar ADÜMN."
    );
  });
