
"use strict";

// --- MÓDULO DE PRODUCCIÓN (STRIPBOARD) ---

async function initProductionBoard() {
    const root = document.getElementById("stripboard-root");
    if (!root) return;
        const projectSelect = document.getElementById("projectSelect");
    const projectId = projectSelect?.value;

    if (!projectId) return;

    // CACHÉ: Si este tablero ya está pintado para este proyecto, no hacemos nada.
    if (root.dataset.loadedProjectId === String(projectId) && root.innerHTML.trim() !== "") {
        return;
    }

    root.innerHTML = `
        <div class="stripboard-wrapper">
            <div class="stripboard-topbar">
                <h2>Plan de Rodaje</h2>
                <button id="approvePlanButton" class="btn-primary">Fijar este plan</button>
            </div>
            <div class="stripboard-container">
                <div class="stripboard-pool" id="stripboard-pool">
                    <h2>Escenas sin asignar</h2>
                    <div id="pool-cards"></div>
                </div>
                <div class="stripboard-days" id="stripboard-days"></div>
            </div>
        </div>
    `;

    try {
        const projectSelect = document.getElementById("projectSelect");
        const projectId = projectSelect?.value;

        if (!projectId) {
            renderBoardMessage("Selecciona un proyecto para ver el plan de rodaje.");
            return;
        }

        const encodedProjectId = encodeURIComponent(projectId);

        const [scheduleResponse, scenesResponse] = await Promise.all([
            fetch(`/api/projects/${encodedProjectId}/schedule-preview`),
            fetch(`/api/projects/${encodedProjectId}/scheduling-input`)
        ]);

        if (!scheduleResponse.ok || !scenesResponse.ok) {
            throw new Error("No fue posible cargar el plan de rodaje.");
        }

        const [scheduleData, scenesData] = await Promise.all([
            scheduleResponse.json(),
            scenesResponse.json()
        ]);

        if (!Array.isArray(scenesData?.scenes)) {
            throw new Error("La respuesta de escenas no tiene el formato esperado.");
        }

        if (!Array.isArray(scheduleData?.best_schedule?.days)) {
            throw new Error("La respuesta del plan no contiene jornadas válidas.");
        }

        // Normalizamos los identificadores para admitir 3 y "3".
        // Se indexa también por production_number como alternativa,
        // porque el plan puede referirse a una escena por su número de producción.
        const sceneById = new Map();
        const sceneByProductionNumber = new Map();

        for (const scene of scenesData.scenes) {
            // El backend devuelve 'scene_id', no 'id'. Normalizamos para no romper el resto.
            if (scene.scene_id !== undefined && scene.scene_id !== null) {
                scene.id = scene.scene_id;
            }

            if (scene.id === undefined || scene.id === null) {
                continue;
            }

            const idKey = normalizeId(scene.id);

            if (!sceneById.has(idKey)) {
                sceneById.set(idKey, scene);
            }

            if (
                scene.production_number !== undefined &&
                scene.production_number !== null &&
                String(scene.production_number).trim() !== ""
            ) {
                const productionKey = normalizeId(scene.production_number);

                if (!sceneByProductionNumber.has(productionKey)) {
                    sceneByProductionNumber.set(productionKey, scene);
                }
            }
        }

        const resolveScene = (id) => {
            if (id === undefined || id === null) {
                return undefined;
            }

            const key = normalizeId(id);

            return sceneById.get(key) ||
                sceneByProductionNumber.get(key);
        };

        renderStripboard(
            scheduleData,
            sceneById,
            resolveScene
        );

        // Conectar el botón de "Fijar plan"
        const approveBtn = document.getElementById("approvePlanButton");
        if (approveBtn) {
            approveBtn.addEventListener("click", async () => {
                try {
                    approveBtn.disabled = true;
                    approveBtn.textContent = "Guardando...";

                    const daysToSave = (scheduleData.best_schedule.days || []).map(day => ({
                        day: day.day,
                        scene_ids: day.scene_ids
                    }));

                    const response = await fetch(`/api/projects/${encodedProjectId}/schedule-manual-order`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            days: daysToSave,
                            shoot_rate_seconds: 420
                        })
                    });

                    if (!response.ok) throw new Error("Error al guardar");

                    approveBtn.textContent = "¡Plan fijado!";
                    setTimeout(() => {
                        approveBtn.textContent = "Fijar este plan";
                        approveBtn.disabled = false;
                    }, 2000);

                } catch (error) {
                    console.error(error);
                    approveBtn.textContent = "Error al guardar";
                    approveBtn.disabled = false;
                }
            });
        }
        root.dataset.loadedProjectId = String(projectId);
    } catch (error) {
        console.error("Error cargando el tablero de producción:", error);

        root.innerHTML = `
            <p class="stripboard-error" role="alert">
                Error al cargar el tablero de producción.
                Comprueba la conexión e inténtalo de nuevo.
            </p>
        `;
    }
}


// Normalización común para las claves de identificación.
function normalizeId(value) {
    return String(value).trim();
}


function renderBoardMessage(message) {
    const poolCards = document.getElementById("pool-cards");

    if (poolCards) {
        poolCards.textContent = message;
    }
}


function renderStripboard(scheduleData, sceneById, resolveScene) {
    const poolCards = document.getElementById("pool-cards");
    const daysContainer = document.getElementById("stripboard-days");

    if (!poolCards || !daysContainer) return;

    const days = scheduleData?.best_schedule?.days || [];

    // Registrar las escenas asignadas usando el ID real de cada escena.
    // Esto evita duplicarlas en el pool si el plan usa production_number.
    const assignedSceneIds = new Set();

    for (const day of days) {
        const sceneIds = Array.isArray(day.scene_ids)
            ? day.scene_ids
            : [];

        for (const id of sceneIds) {
            const scene = resolveScene(id);

            if (scene) {
                assignedSceneIds.add(normalizeId(scene.id));
            }
        }
    }

    // Escenas sin asignar.
    const unassignedScenes = [...sceneById.values()].filter(
        scene => !assignedSceneIds.has(normalizeId(scene.id))
    );

    poolCards.innerHTML = unassignedScenes.length
        ? unassignedScenes.map(scene => renderSceneCard(scene)).join("")
        : `<div class="stripboard-empty">Todas las escenas están asignadas.</div>`;

    // Pintar las jornadas y mantener el orden del plan del backend.
    daysContainer.innerHTML = days.map(day => {
        const sceneIds = Array.isArray(day.scene_ids)
            ? day.scene_ids
            : [];

        const dayScenes = sceneIds
            .map(id => resolveScene(id))
            .filter(Boolean);

        const cardsHtml = dayScenes.length
            ? dayScenes.map(scene => renderSceneCard(scene)).join("")
            : `<div class="stripboard-empty">Sin escenas.</div>`;

        const runtimeSeconds = normalizeRuntime(day.runtime_seconds);
        const runtimeFormatted = formatRuntime(runtimeSeconds);
        const dayNumber = escapeHtml(day.day ?? "");

        return `
            <div class="strip-day" data-day="${dayNumber}">
                <div class="strip-day-header">
                    <span>Día ${dayNumber}</span>
                </div>
                <div class="strip-day-stats">
                    ${dayScenes.length} escenas | ${runtimeFormatted}
                </div>
                <div class="strip-day-cards">
                    ${cardsHtml}
                </div>
            </div>
        `;
    }).join("");
}


// Validar la duración recibida del backend.
function normalizeRuntime(value) {
    const seconds = Number(value);

    if (!Number.isFinite(seconds) || seconds < 0) {
        return 0;
    }

    return Math.floor(seconds);
}


// Mostrar minutos y segundos, admitiendo jornadas superiores a 60 minutos.
function formatRuntime(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}


// Normalizar acentos y mayúsculas para clasificar los colores.
function normalizeLabel(value) {
    return String(value ?? "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .trim()
        .toUpperCase();
}


function getSceneColorClass(scene) {
    const intExt = normalizeLabel(scene.int_ext);
    const time = normalizeLabel(scene.time_of_day);

    const isExterior = /\bEXT\b/.test(intExt);
    const isInterior = /\bINT\b/.test(intExt);

    const isNight = /\bNOCHE\b|\bNIGHT\b/.test(time);
    const isDay = /\bDIA\b|\bDAY\b/.test(time);

    if (isExterior && isNight) return "ext-night";
    if (isExterior && isDay) return "ext-day";
    if (isInterior && isNight) return "int-night";
    if (isInterior && isDay) return "int-day";

    // No inventar una clasificación cuando los datos son incompletos.
    return "scene-unclassified";
}


function renderSceneCard(scene) {
    const colorClass = getSceneColorClass(scene);

    const productionNumber =
        scene.production_number ?? scene.scene_number ?? scene.id;

    const location = String(scene.location ?? "").trim() || "Sin locación";
    const intExt = String(scene.int_ext ?? "").trim();
    const time = String(scene.time_of_day ?? "").trim();

    const heading = `ESC. ${productionNumber}`;
    const description = [location, intExt, time]
        .filter(Boolean)
        .join(" - ");

    return `
        <div
            class="strip-card ${colorClass}"
            data-scene-id="${escapeHtml(scene.id)}"
        >
            <div class="strip-card-header">
                ${escapeHtml(heading)}
            </div>
            <div class="strip-card-body">
                ${escapeHtml(description)}
            </div>
        </div>
    `;
}


// Escapar los valores dinámicos antes de insertarlos en HTML.
function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => {
        const entities = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        };

        return entities[character];
    });
}


// Exponer la función para que app.js pueda llamarla.
window.initProductionBoard = initProductionBoard;