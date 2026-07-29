
const state = {
  projects: [],
  project: null,
  scenes: [],
  activeSceneId: null,

  // Cada escena administra su propio guardado.
  saveTimers: new Map(),
  saveRevisions: new Map(),
  savingScenes: new Set(),

  analysisTimer: null,

  activeLine: null,
  isRendering: false,
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

 if (
  /^(INT\.|EXT\.|INT\/EXT\.|EXT\/INT\.|I\/E\.|E\/I\.)\s*/i.test(value)
) {
    return "heading";
}

  if (
    value.startsWith("(") &&
    value.endsWith(")")
  ) {
    return "parenthetical";
  }

  if (
    /:$/.test(value) &&
    /^(CORTE|FUNDIDO|DISOLVENCIA|MATCH CUT|SALTO|IRIS|WIPE|FADE)/i.test(
      value
    )
  ) {
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

  result.push({
    type: "heading",
    text: heading || "INT. LOCACIÓN - DÍA",
  });

  const bodyLines =
    String(scene.body || "")
      .split(/\r?\n/);

  let previousType = "heading";

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

  if (result.length === 1) {
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

  line.spellcheck =
    type !== "character" &&
    type !== "heading";

  line.setAttribute(
    "role",
    "textbox"
  );

  line.setAttribute(
    "aria-label",
    LINE_LABELS[type] || "Línea"
  );

  line.textContent = text;

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
        "heading",
        "INT. LOCACIÓN - DÍA"
      ),
      createLine(
        "action",
        ""
      )
    );

    return;
  }

  let heading = lines.find(
    line => getLineType(line) === "heading"
  );

  if (!heading) {
    heading = createLine(
      "heading",
      "INT. LOCACIÓN - DÍA"
    );

    sceneNode.prepend(heading);
  } else if (
    heading !== sceneNode.firstElementChild
  ) {
    sceneNode.prepend(heading);
  }

  lines = lineElements(sceneNode);

  if (lines.length === 1) {
    sceneNode.appendChild(
      createLine(
        "action",
        ""
      )
    );
  }

  const extraHeadings =
    lineElements(sceneNode).filter(
      (line, index) =>
        index > 0 &&
        getLineType(line) === "heading"
    );

  extraHeadings.forEach(
    splitSceneAtHeading
  );
}

function renderScreenplay() {
  const editor = $("#screenplayEditor");

  state.isRendering = true;
  editor.innerHTML = "";

  if (!state.scenes.length) {
    editor.appendChild(
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

function setLineType(line, type) {
  if (
    !line ||
    !LINE_TYPES.includes(type)
  ) {
    return;
  }

  LINE_TYPES.forEach(item => {
    line.classList.remove(item);
  });

  line.classList.add(type);
  line.dataset.type = type;

  line.setAttribute(
    "aria-label",
    LINE_LABELS[type] || "Línea"
  );

  line.spellcheck =
    type !== "character" &&
    type !== "heading";

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
      placeCaretAtEnd(line);
    }
  }

  updateModeLabel(type);

  if (type === "heading") {
    splitSceneAtHeading(line);
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
    return "heading";
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
    /^(INT\.|EXT\.|INT\/EXT\.|EXT\/INT\.|I\/E\.|E\/I\.)$/i.test(
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

function handleLineKeydown(event) {
  const line =
    event.currentTarget;

  const type =
    getLineType(line);

 if (event.key === "Tab") {
  event.preventDefault();

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

      splitSceneAtHeading(
        nextLine
      );
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

    return;
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
    /^(INT\.|EXT\.|INT\/EXT\.|EXT\/INT\.|I\/E\.|E\/I\.)\s*/i.test(
      lineText
    )
  ) {
    setLineType(
      line,
      "heading"
    );

    return;
  }

  const sceneNode =
    line.closest(".script-scene");

  if (
    getLineType(line) === "heading"
  ) {
    updateSceneHeadingFromDom(
      sceneNode
    );
  }

  scheduleSceneSave(
    sceneNode
  );
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

    if (type === "heading") {
      splitSceneAtHeading(next);
    }
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

  if (
    !scene ||
    !headingLine
  ) {
    return;
  }

  scene.heading =
    (
      headingLine.textContent ||
      ""
    ).trim();

  renderSceneList();
}

async function splitSceneAtHeading(line) {
  const currentScene =
    line.closest(".script-scene");

  if (!currentScene) {
    return;
  }

  const isFirstLine =
    currentScene.firstElementChild ===
    line;

  if (isFirstLine) {
    scheduleSceneSave(
      currentScene
    );

    return;
  }

  if (!state.project) {
    return;
  }

  setSaveState(
    "Creando escena…",
    "saving"
  );

  try {
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

    const newSceneNode =
      document.createElement(
        "section"
      );

    newSceneNode.className =
      "script-scene";

    newSceneNode.dataset.sceneId =
      String(created.id);

    newSceneNode.dataset.sceneNumber =
      String(
        created.scene_number
      );

    let moving = line;

    while (moving) {
      const next =
        moving.nextElementSibling;

      newSceneNode.appendChild(
        moving
      );

      moving = next;
    }

    if (
      newSceneNode.children.length === 1
    ) {
      newSceneNode.appendChild(
        createLine(
          "action",
          ""
        )
      );
    }

    currentScene.after(
      newSceneNode
    );

    const currentIndex =
      state.scenes.findIndex(
        scene =>
          scene.id ===
          Number(
            currentScene.dataset.sceneId
          )
      );

    state.scenes.splice(
      currentIndex + 1,
      0,
      created
    );

    renumberScenesLocally();

    updateSceneHeadingFromDom(
      newSceneNode
    );

    await saveSceneNode(
      currentScene
    );

    await saveSceneNode(
      newSceneNode
    );

    state.activeSceneId =
      created.id;

    renderSceneList();

    setActiveScene(
      created.id,
      {
        scroll: false,
        focus: false,
      }
    );

    setSaveState(
      "Guardado",
      "saved"
    );
  } catch (error) {
    console.error(error);

    setSaveState(
      "Error al crear escena",
      "error"
    );
  }
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
    ) ||
    lines[0];

  const heading =
    (headingLine?.textContent || "")
      .trim();

  const bodyLines = lines
    .filter(line => line !== headingLine)
    .map(line => line.textContent || "");

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
  const labels = {
    heading:
      "Encabezados",

    action:
      "Acción",

    character:
      "Personajes",

    dialogue:
      "Diálogos",

    parenthetical:
      "Parentéticos",

    transition:
      "Transiciones",
  };

  const counts =
    analysis?.counts || {};

  const chips =
    Object
      .entries(labels)
      .map(
        ([key, label]) => `
          <div class="analysis-chip">
            <span>
              ${label}
            </span>

            <strong>
              ${counts[key] || 0}
            </strong>
          </div>
        `
      )
      .join("");

  const characters =
    analysis?.characters?.length
      ? `
        <div class="analysis-characters">
          <strong>
            Detectados:
          </strong>

          ${
            analysis.characters
              .map(escapeHtml)
              .join(", ")
          }
        </div>
      `
      : `
        <div class="analysis-characters">
          Aún no se detectan personajes.
        </div>
      `;

  $("#scriptAnalysis")
    .innerHTML = `
      <div class="analysis-grid">
        ${chips}
      </div>

      ${characters}
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

  if (
    !scene
      ?.breakdown_items
      ?.length
  ) {
    container.innerHTML = `
      <div class="empty">
        No hay elementos confirmados.
      </div>
    `;

    return;
  }

  container.innerHTML =
    scene.breakdown_items
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
          </div>
        `
      )
      .join("");
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
              "confirmed",
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

    const heading =
      node.querySelector(
        ".script-line.heading"
      );

    if (heading) {
      focusLine(
        heading,
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
  const data =
    await request(
      `/api/projects/${projectId}`
    );

  state.project =
    data.project;

  state.scenes =
    data.scenes || [];

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
  }

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
      "No fue posible iniciar Trumbo."
    );
  });
