const state = {
  projects: [],
  project: null,
  scenes: [],
  activeSceneId: null,
  saveTimer: null,
};

const $ = selector => document.querySelector(selector);

function formatSeconds(total) {
  const minutes = Math.floor(total / 60).toString().padStart(2, "0");
  const seconds = (total % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: "Error inesperado" }));
    throw new Error(detail.detail || "Error inesperado");
  }
  return response.json();
}

async function loadProjects(preferredProjectId = null) {
  state.projects = await request("/api/projects");
  $("#projectSelect").innerHTML = state.projects
    .map(project => `<option value="${project.id}">${escapeHtml(project.title)}</option>`)
    .join("");

  const projectId = preferredProjectId || state.projects[0]?.id;
  if (projectId) await loadProject(projectId);
}

async function loadProject(projectId) {
  const data = await request(`/api/projects/${projectId}`);
  state.project = data.project;
  state.scenes = data.scenes;
  state.activeSceneId = state.scenes[0]?.id ?? null;

  $("#projectSelect").value = String(projectId);
  $("#projectTitle").value = state.project.title;
  renderSceneList();
  renderActiveScene();
  await updateProjectRuntime();
}

function activeScene() {
  return state.scenes.find(scene => scene.id === state.activeSceneId);
}

function renderSceneList() {
  const container = $("#sceneList");
  if (!state.scenes.length) {
    container.innerHTML = `<div class="empty">El proyecto aún no tiene escenas.</div>`;
    return;
  }

  container.innerHTML = state.scenes.map(scene => `
    <div class="scene-card ${scene.id === state.activeSceneId ? "active" : ""}" data-scene-id="${scene.id}">
      <div class="scene-number">ESCENA ${scene.scene_number}</div>
      <div class="scene-card-heading">${escapeHtml(scene.heading || "Sin encabezado")}</div>
      <div class="scene-card-runtime">${formatSeconds(scene.runtime_seconds)}</div>
    </div>
  `).join("");

  container.querySelectorAll(".scene-card").forEach(card => {
    card.addEventListener("click", () => {
      state.activeSceneId = Number(card.dataset.sceneId);
      renderSceneList();
      renderActiveScene();
    });
  });
}

function renderActiveScene() {
  const scene = activeScene();
  const disabled = !scene;

  ["#sceneHeading", "#sceneBody", "#sceneSynopsis"].forEach(selector => {
    $(selector).disabled = disabled;
  });

  if (!scene) {
    $("#sceneIdentity").textContent = "SIN ESCENA";
    $("#sceneHeading").value = "";
    $("#sceneBody").value = "";
    $("#sceneSynopsis").value = "";
    $("#sceneRuntime").textContent = "00:00";
    $("#notesList").innerHTML = "";
    $("#breakdownList").innerHTML = "";
    return;
  }

  $("#sceneIdentity").textContent = `ESCENA ${scene.scene_number}`;
  $("#sceneHeading").value = scene.heading;
  $("#sceneBody").value = scene.body;
  $("#sceneSynopsis").value = scene.synopsis;
  $("#sceneRuntime").textContent = formatSeconds(scene.runtime_seconds);
  renderNotes(scene);
  renderBreakdown(scene);
}

function scheduleSceneSave() {
  clearTimeout(state.saveTimer);
  $("#saveState").textContent = "Editando…";
  state.saveTimer = setTimeout(saveActiveScene, 550);
}

async function saveActiveScene() {
  const scene = activeScene();
  if (!scene) return;

  $("#saveState").textContent = "Guardando…";
  try {
    const updated = await request(`/api/scenes/${scene.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        heading: $("#sceneHeading").value,
        body: $("#sceneBody").value,
        synopsis: $("#sceneSynopsis").value,
      }),
    });

    Object.assign(scene, updated);
    $("#sceneRuntime").textContent = formatSeconds(scene.runtime_seconds);
    $("#saveState").textContent = "Guardado";
    renderSceneList();
    await updateProjectRuntime();
  } catch (error) {
    $("#saveState").textContent = "Error al guardar";
    console.error(error);
  }
}

async function updateProjectRuntime() {
  if (!state.project) return;
  const runtime = await request(`/api/projects/${state.project.id}/runtime`);
  $("#projectRuntime").textContent = runtime.formatted;
}

function renderNotes(scene) {
  const container = $("#notesList");
  if (!scene.notes?.length) {
    container.innerHTML = `<div class="empty">No hay notas.</div>`;
    return;
  }

  container.innerHTML = scene.notes.map(note => `
    <div class="item">
      <div class="item-meta">${escapeHtml(note.category)}</div>
      <div>${escapeHtml(note.body)}</div>
    </div>
  `).join("");
}

function renderBreakdown(scene) {
  const container = $("#breakdownList");
  if (!scene.breakdown_items?.length) {
    container.innerHTML = `<div class="empty">No hay elementos confirmados.</div>`;
    return;
  }

  container.innerHTML = scene.breakdown_items.map(item => `
    <div class="item">
      <div class="item-meta">${escapeHtml(item.category)} · ${escapeHtml(item.state)}</div>
      <div>${escapeHtml(item.name)}</div>
    </div>
  `).join("");
}

function proposeSynopsis() {
  const body = $("#sceneBody").value.trim();
  if (!body) return;

  const normalized = body.replace(/\n+/g, " ").replace(/\s+/g, " ").trim();
  const firstSentence = normalized.match(/^(.{1,220}?[.!?])(?:\s|$)/)?.[1] || normalized.slice(0, 180);

  $("#sceneSynopsis").value = firstSentence;
  scheduleSceneSave();
}

async function createProject() {
  const title = window.prompt("Título del proyecto");
  if (!title?.trim()) return;

  const project = await request("/api/projects", {
    method: "POST",
    body: JSON.stringify({ title: title.trim(), format: "feature" }),
  });
  await loadProjects(project.id);
}

async function createScene() {
  if (!state.project) return;

  const scene = await request(`/api/projects/${state.project.id}/scenes`, {
    method: "POST",
    body: JSON.stringify({}),
  });

  scene.notes = [];
  scene.breakdown_items = [];
  state.scenes.push(scene);
  state.activeSceneId = scene.id;
  renderSceneList();
  renderActiveScene();
}

async function addNote() {
  const scene = activeScene();
  const body = $("#noteInput").value.trim();
  if (!scene || !body) return;

  const note = await request(`/api/scenes/${scene.id}/notes`, {
    method: "POST",
    body: JSON.stringify({ body, category: "general" }),
  });

  scene.notes = scene.notes || [];
  scene.notes.unshift(note);
  $("#noteInput").value = "";
  renderNotes(scene);
}

async function addBreakdownItem() {
  const scene = activeScene();
  const name = $("#breakdownName").value.trim();
  const category = $("#breakdownCategory").value;
  if (!scene || !name) return;

  const item = await request(`/api/scenes/${scene.id}/breakdown`, {
    method: "POST",
    body: JSON.stringify({ category, name, source: "manual", state: "confirmed" }),
  });

  scene.breakdown_items = scene.breakdown_items || [];
  scene.breakdown_items.push(item);
  $("#breakdownName").value = "";
  renderBreakdown(scene);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

$("#projectSelect").addEventListener("change", event => loadProject(event.target.value));
$("#newProjectButton").addEventListener("click", createProject);
$("#newSceneButton").addEventListener("click", createScene);
$("#sceneHeading").addEventListener("input", scheduleSceneSave);
$("#sceneBody").addEventListener("input", scheduleSceneSave);
$("#sceneSynopsis").addEventListener("input", scheduleSceneSave);
$("#suggestSynopsisButton").addEventListener("click", proposeSynopsis);
$("#addNoteButton").addEventListener("click", addNote);
$("#addBreakdownButton").addEventListener("click", addBreakdownItem);

$("#projectTitle").addEventListener("change", async event => {
  if (!state.project) return;
  const title = event.target.value.trim();
  if (!title) return;

  const updated = await request(`/api/projects/${state.project.id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
  await loadProjects(updated.id);
});

document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(item => item.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(panel => panel.classList.remove("active"));
    tab.classList.add("active");
    $(`#panel-${tab.dataset.tab}`).classList.add("active");
  });
});

loadProjects().catch(error => {
  console.error(error);
  alert("No fue posible iniciar Trumbo.");
});
