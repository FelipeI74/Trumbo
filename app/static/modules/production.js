
"use strict";

// --- MÓDULO DE PRODUCCIÓN (STRIPBOARD) ---

let productionSceneById = new Map();
let productionResolveScene = null;
let currentViewMode = "proyecto";
let productionProjectId = null;
let productionLoadToken = 0;

async function initProductionBoard() {
    const loadToken = ++productionLoadToken;
    const root = document.getElementById("stripboard-root");
    if (!root) return;
    closeSceneModal();
    root.innerHTML = "";
    delete root.dataset.loadedProjectId;
    productionProjectId = null;

    const projectSelect = document.getElementById("projectSelect");
    const projectId = projectSelect?.value;

    if (!projectId) {
        root.textContent = "Selecciona un proyecto para ver el plan de rodaje.";
        return;
    }
    productionProjectId = projectId;

    ensureSceneModal(root);

    root.innerHTML = `
        <div class="stripboard-wrapper">
            <div class="stripboard-topbar">
                <h2>Plan de Rodaje</h2>
                <div class="view-mode-controls" aria-label="Filtrar jornadas">
                    <button id="btnViewDaily" class="view-mode-btn" type="button">Diario</button>
                    <button id="btnViewWeekly" class="view-mode-btn" type="button">Semanal</button>
                    <button id="btnViewProject" class="view-mode-btn active" type="button">Proyecto</button>
                </div>
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

        const [scheduleResponse, scenesResponse, storyboardResponse] = await Promise.all([
            fetch(`/api/projects/${encodedProjectId}/schedule-preview`, { cache: "no-store" }),
            fetch(`/api/projects/${encodedProjectId}/scheduling-input`, { cache: "no-store" }),
            fetch(`/api/projects/${encodedProjectId}/storyboard`, { cache: "no-store" })
        ]);

        if (!scheduleResponse.ok || !scenesResponse.ok || !storyboardResponse.ok) {
            throw new Error("No fue posible cargar el plan de rodaje.");
        }

        const [scheduleData, scenesData, storyboardData] = await Promise.all([
            scheduleResponse.json(),
            scenesResponse.json(),
            storyboardResponse.json()
        ]);

        if (loadToken !== productionLoadToken) return;

        if (!Array.isArray(scenesData?.scenes)) {
            throw new Error("La respuesta de escenas no tiene el formato esperado.");
        }

        if (!Array.isArray(scheduleData?.best_schedule?.days)) {
            throw new Error("La respuesta del plan no contiene jornadas válidas.");
        }

        window.lastSchedulingInput = scenesData;

        // Normalizamos los identificadores para admitir 3 y "3".
        // Se indexa también por production_number como alternativa,
        // porque el plan puede referirse a una escena por su número de producción.
                const sceneById = new Map();
        const sceneByProductionNumber = new Map();

        // Crear un diccionario de planos por escena
        const shotsBySceneId = new Map();
        if (storyboardData && storyboardData.scenes) {
            for (const sbScene of storyboardData.scenes) {
                shotsBySceneId.set(sbScene.scene_id, sbScene.shots || []);
            }
        }

        for (const scene of scenesData.scenes) {
            // El backend devuelve 'scene_id', no 'id'. Normalizamos para no romper el resto.
            if (scene.scene_id !== undefined && scene.scene_id !== null) {
                scene.id = scene.scene_id;
            }

            // Asignar los planos a la escena
            scene.shots = shotsBySceneId.get(scene.id) || [];

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

        productionSceneById = sceneById;

        const resolveScene = (id) => {
            if (id === undefined || id === null) {
                return undefined;
            }

            const key = normalizeId(id);

            return sceneById.get(key) ||
                sceneByProductionNumber.get(key);
        };

        productionResolveScene = resolveScene;
        renderStripboard(
            scheduleData,
            sceneById,
            resolveScene
        );
        bindViewModeButtons(sceneById, resolveScene);

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
        if (loadToken !== productionLoadToken) return;
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
    window.lastScheduleData = scheduleData;

    const poolCards = document.getElementById("pool-cards");
    const daysContainer = document.getElementById("stripboard-days");

    if (!poolCards || !daysContainer) return;
    ensureSceneDragAndDrop(daysContainer);

    const allDays = scheduleData?.best_schedule?.days || [];
    let days = allDays;
    if (currentViewMode === "diario") days = days.slice(0, 1);
    if (currentViewMode === "semanal") days = days.slice(0, 5);

    // Registrar las escenas asignadas usando el ID real de cada escena.
    // Esto evita duplicarlas en el pool si el plan usa production_number.
    const assignedSceneIds = new Set();

    for (const day of allDays) {
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

        const runtimeSeconds = normalizeRuntime(day.runtime_seconds);
        const runtimeFormatted = formatRuntime(runtimeSeconds);
        const dayNumber = escapeHtml(day.day ?? "");
        const numericDayNumber = Number(day.day);
        const callSheetDayNumber = Number.isSafeInteger(numericDayNumber)
            ? numericDayNumber
            : "null";
        const cardsHtml = dayScenes.length
            ? dayScenes.map(scene =>
                renderSceneCard(scene, day.day ?? "", runtimeFormatted)
            ).join("")
            : `<div class="stripboard-empty">Sin escenas.</div>`;

        return `
            <div class="strip-day ${currentViewMode === "diario" ? "daily-view-active" : ""}" data-day="${dayNumber}">
                <div class="strip-day-header" style="display: flex; justify-content: space-between; align-items: center;">
                    <span>Día ${dayNumber}</span>
                    <button class="btn-call-sheet" type="button" onclick="window.openCallSheet(${callSheetDayNumber})" style="background: #333; color: #d8a64f; border: 1px solid #d8a64f; padding: 2px 8px; border-radius: 4px; font-size: 12px; cursor: pointer;">📄 Call Sheet</button>
                </div>
                <div class="strip-day-stats">
                    ${dayScenes.length} escenas | ${day.shots_count || 0} planos | ${runtimeFormatted}
                </div>
                <div class="strip-day-cards">
                    ${cardsHtml}
                </div>
            </div>
        `;
    }).join("");
}


function bindViewModeButtons(sceneById, resolveScene) {
    const buttons = [
        [document.getElementById("btnViewDaily"), "diario"],
        [document.getElementById("btnViewWeekly"), "semanal"],
        [document.getElementById("btnViewProject"), "proyecto"]
    ];

    for (const [button, mode] of buttons) {
        if (!button) continue;

        button.classList.toggle("active", currentViewMode === mode);
        button.addEventListener("click", () => {
            currentViewMode = mode;

            for (const [viewButton, viewMode] of buttons) {
                viewButton?.classList.toggle("active", currentViewMode === viewMode);
            }

            if (window.lastScheduleData) {
                renderStripboard(
                    window.lastScheduleData,
                    sceneById,
                    resolveScene
                );
            }
        });
    }
}


function ensureSceneDragAndDrop(daysContainer) {
    const root = document.getElementById("stripboard-root");
    if (!root) return;

    if (!root.dataset.sceneDragEventsBound) {
        root.addEventListener("dragstart", event => {
            const card = event.target instanceof Element
                ? event.target.closest(".strip-card[data-scene-id]")
                : null;
            if (!card || !root.contains(card)) return;

            window.draggedSceneId = card.dataset.sceneId;
            window.draggedSceneElement = card;
            window.sceneCardDragCompletedAt = 0;
            if (event.dataTransfer) {
                event.dataTransfer.setData("text/plain", card.dataset.sceneId);
                event.dataTransfer.effectAllowed = "move";
            }
        });

        root.addEventListener("dragend", () => {
            window.sceneCardDragCompletedAt = Date.now();
            window.draggedSceneId = null;
            window.draggedSceneElement = null;
        });
        root.dataset.sceneDragEventsBound = "true";
    }

    if (daysContainer.dataset.dragDropBound) return;

    daysContainer.addEventListener("dragover", event => {
        if (!window.draggedSceneId) return;
        const day = event.target instanceof Element
            ? event.target.closest(".strip-day")
            : null;
        if (!day || !daysContainer.contains(day)) return;

        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    });

    daysContainer.addEventListener("drop", async event => {
        const card = window.draggedSceneElement;
        const sceneId = window.draggedSceneId;
        const day = event.target instanceof Element
            ? event.target.closest(".strip-day")
            : null;
        if (!sceneId || !card || !day || !daysContainer.contains(day)) return;

        event.preventDefault();
        const dayCards = day.querySelector(".strip-day-cards");
        if (!dayCards) return;

        const sourceDayCards = card.closest(".strip-day-cards");
        dayCards.querySelectorAll(".stripboard-empty").forEach(empty =>
            empty.remove()
        );
        dayCards.append(card);
        card.dataset.day = day.dataset.day;
        window.draggedSceneId = null;
        window.draggedSceneElement = null;
        window.sceneCardDragCompletedAt = Date.now();

        const visibleDays = new Map(
            [...daysContainer.querySelectorAll(".strip-day")].map(stripDay => [
                String(stripDay.dataset.day),
                {
                    day: Number(stripDay.dataset.day),
                    scene_ids: [...stripDay.querySelectorAll(
                        ".strip-day-cards .strip-card[data-scene-id]"
                    )].map(sceneCard => Number(sceneCard.dataset.sceneId))
                }
            ])
        );
        const existingDays = window.lastScheduleData?.best_schedule?.days || [];
        const days = existingDays.map(existingDay =>
            visibleDays.get(String(existingDay.day)) || {
                day: existingDay.day,
                scene_ids: existingDay.scene_ids
            }
        );
        if (sourceDayCards && !sourceDayCards.querySelector(".strip-card")) {
            const emptyMessage = document.createElement("div");
            emptyMessage.className = "stripboard-empty";
            emptyMessage.textContent = "Sin escenas.";
            sourceDayCards.append(emptyMessage);
        }

        try {
            const response = await fetch(
                `/api/projects/${encodeURIComponent(productionProjectId)}/schedule-manual-order`,
                {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        days,
                        shoot_rate_seconds: 420
                    })
                }
            );
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(
                    errorData.detail ||
                    "Error al guardar el orden. Revisa las reglas de DÍA/NOCHE."
                );
            }

            const savedSchedule = await response.json();
            if (Array.isArray(savedSchedule.days)) {
                window.lastScheduleData.best_schedule.days = savedSchedule.days;
            }
        } catch (error) {
            console.error("Error guardando el nuevo orden de escenas:", error);
            window.alert(
                error.message ||
                "Error al guardar el orden. Revisa las reglas de DÍA/NOCHE."
            );
            const root = document.getElementById("stripboard-root");
            if (root) root.dataset.loadedProjectId = "";
            await initProductionBoard();
        }
    });

    daysContainer.dataset.dragDropBound = "true";
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
    const time = normalizeLabel(
        scene.shoot_time_override || scene.time_of_day
    );

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


function isSceneScheduledAtNight(scene) {
    const time = normalizeLabel(
        scene.shoot_time_override || scene.time_of_day
    );
    return /\bNOCHE\b|\bNIGHT\b/.test(time);
}


function getShootTimeOverrideTarget(scene) {
    return isSceneScheduledAtNight(scene) ? "DÍA" : "NOCHE";
}


function renderSceneCard(scene, dayNumber = "", runtimeFormatted = "") {
    const colorClass = getSceneColorClass(scene);

    const productionNumber =
        scene.production_number ?? scene.scene_number ?? scene.id;

    const location = String(scene.location ?? "").trim() || "Sin locación";
    const intExt = String(scene.int_ext ?? "").trim();
    const time = String(scene.time_of_day ?? "").trim();
    const isOriginallyNight = /\bNOCHE\b|\bNIGHT\b/.test(normalizeLabel(time));
    const overrideTarget = getShootTimeOverrideTarget(scene);
    const shootTimeIndicator = isOriginallyNight
        ? `<button
                class="strip-card-shoot-time"
                type="button"
                draggable="false"
                data-shoot-time-toggle
                data-shoot-time-target="${overrideTarget}"
                aria-label="Cambiar grabación a ${overrideTarget}"
                title="Cambiar grabación a ${overrideTarget}"
            >${scene.shoot_time_override === "DÍA" ? "☀️" : "🌙"}</button>`
        : "";

    const heading = `ESC. ${productionNumber}`;
    const description = [location, intExt, time]
        .filter(Boolean)
        .join(" - ");

    // Generar el resumen de planos (ej: "2 PG, 1 PD")
    let shotsSummary = "";
    if (scene.shots && scene.shots.length > 0) {
        const typeCounts = {};
        scene.shots.forEach(shot => {
            const type = shot.shot_type || "PM";
            typeCounts[type] = (typeCounts[type] || 0) + 1;
        });
        const parts = Object.entries(typeCounts).map(([type, count]) => `${count} ${type}`);
        shotsSummary = `<div style="font-size: 0.85em; margin-top: 4px; opacity: 0.8; color: #d8a64f;">${parts.join(", ")}</div>`;
    }

    return `
        <div
            class="strip-card ${colorClass}"
            data-scene-id="${escapeHtml(scene.id)}"
            data-color-class="${colorClass}"
            data-day="${escapeHtml(dayNumber)}"
            data-runtime="${escapeHtml(runtimeFormatted)}"
            draggable="true"
            role="button"
            tabindex="0"
            aria-haspopup="dialog"
        >
            <div class="strip-card-header">
                ${escapeHtml(heading)}
            </div>
            <div class="strip-card-body">
                ${escapeHtml(description)}
                ${shotsSummary}
                ${shootTimeIndicator}
            </div>
        </div>
    `;
}


function ensureSceneModal(root) {
    if (!root.dataset.sceneModalBound) {
        root.addEventListener("click", event => {
            const card = event.target instanceof Element
                ? event.target.closest(".strip-card[data-scene-id]")
                : null;
            if (!card || !root.contains(card)) return;

            const timeToggle = event.target instanceof Element
                ? event.target.closest("[data-shoot-time-toggle]")
                : null;
            if (timeToggle) {
                event.preventDefault();
                event.stopPropagation();
                const scene = productionSceneById.get(
                    normalizeId(card.dataset.sceneId)
                );
                if (scene) {
                    updateSceneShootTime(
                        scene,
                        timeToggle.dataset.shootTimeTarget
                    );
                }
                return;
            }

            if (
                window.sceneCardDragCompletedAt &&
                Date.now() - window.sceneCardDragCompletedAt < 500
            ) {
                event.preventDefault();
                event.stopPropagation();
                window.sceneCardDragCompletedAt = 0;
                return;
            }
            window.openSceneModal(
                card.dataset.sceneId,
                card,
                card.dataset.colorClass,
                card.dataset.day,
                card.dataset.runtime
            );
        });

        root.addEventListener("keydown", event => {
            const card = event.target instanceof Element
                ? event.target.closest(".strip-card[data-scene-id]")
                : null;
            const timeToggle = event.target instanceof Element
                ? event.target.closest("[data-shoot-time-toggle]")
                : null;
            if (
                card &&
                root.contains(card) &&
                !timeToggle &&
                (event.key === "Enter" || event.key === " ")
            ) {
                event.preventDefault();
                window.openSceneModal(
                    card.dataset.sceneId,
                    card,
                    card.dataset.colorClass,
                    card.dataset.day,
                    card.dataset.runtime
                );
            }
        });

        root.dataset.sceneModalBound = "true";
    }

    if (document.getElementById("sceneModalOverlay")) return;

    document.body.insertAdjacentHTML("beforeend", `
        <div id="sceneModalOverlay" class="scene-modal-overlay" aria-hidden="true">
            <section
                class="scene-modal-content"
                role="dialog"
                aria-modal="true"
                aria-labelledby="modalSceneTitle"
            >
                <button class="scene-modal-close" type="button" aria-label="Cerrar detalle de escena">×</button>
                <h2 id="modalSceneTitle">ESCENA</h2>
                <div id="modalSceneBody"></div>
            </section>
        </div>
    `);

    const overlay = document.getElementById("sceneModalOverlay");
    const closeButton = overlay.querySelector(".scene-modal-close");
    closeButton.addEventListener("click", closeSceneModal);
    overlay.addEventListener("click", event => {
        if (event.target === overlay) {
            closeSceneModal();
        }
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && overlay.classList.contains("active")) {
            closeSceneModal();
        }
    });
}


let sceneModalTrigger = null;

function closeSceneModal() {
    const overlay = document.getElementById("sceneModalOverlay");
    if (!overlay) return;

    overlay.classList.remove("active");
    overlay.setAttribute("aria-hidden", "true");
    sceneModalTrigger?.focus();
    sceneModalTrigger = null;
}


async function updateSceneShootTime(scene, shootTimeOverride) {
    try {
        const response = await fetch(
            `/api/scenes/${encodeURIComponent(scene.id)}`,
            {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    shoot_time_override: shootTimeOverride
                })
            }
        );
        if (!response.ok) {
            throw new Error(`Error HTTP ${response.status}`);
        }

        const updatedScene = await response.json();
        scene.shoot_time_override = updatedScene.shoot_time_override;
        if (window.lastScheduleData && productionResolveScene) {
            renderStripboard(
                window.lastScheduleData,
                productionSceneById,
                productionResolveScene
            );
        }

        const modalContent = document.querySelector(
            "#sceneModalOverlay .scene-modal-content"
        );
        const modalColors = {
            "int-day": "#f4f0e8",
            "ext-day": "#ffe599",
            "int-night": "#6fa8dc",
            "ext-night": "#93c47d",
            "scene-unclassified": "#777"
        };
        const colorClass = getSceneColorClass(scene);
        if (modalContent) {
            modalContent.style.borderTop =
                `4px solid ${modalColors[colorClass] || modalColors["scene-unclassified"]}`;
        }

        const modalStatus = document.getElementById("modalShootTimeStatus");
        if (modalStatus) {
            modalStatus.textContent = scene.shoot_time_override
                ? ` · ${scene.shoot_time_override === "DÍA" ? "☀️" : "🌙"} Rodaje ${scene.shoot_time_override}`
                : "";
        }

        const modalButton = document.getElementById("modalShootTimeToggle");
        if (modalButton) {
            const nextTarget = getShootTimeOverrideTarget(scene);
            modalButton.dataset.shootTimeTarget = nextTarget;
            modalButton.textContent =
                `Grabar de ${nextTarget === "DÍA" ? "Día" : "Noche"}`;
        }
    } catch (error) {
        console.error("Error actualizando el horario de rodaje de la escena:", error);
        window.alert("No se pudo actualizar el horario de rodaje.");
    }
}


window.openSceneModal = async function(
    sceneId,
    trigger = null,
    colorClass = "scene-unclassified",
    dayNumber = "",
    runtimeFormatted = ""
) {
    const overlay = document.getElementById("sceneModalOverlay");
    const title = document.getElementById("modalSceneTitle");
    const body = document.getElementById("modalSceneBody");
    if (!overlay || !title || !body) return;

    const scene = productionSceneById.get(normalizeId(sceneId));
    body.replaceChildren();
    const requestId = Number(body.dataset.breakdownRequestId || 0) + 1;
    body.dataset.breakdownRequestId = String(requestId);

    if (scene) {
        const productionNumber =
            scene.production_number ?? scene.scene_number ?? scene.id;
        title.textContent = `ESCENA ${productionNumber}`;

        const modalContent = overlay.querySelector(".scene-modal-content");
        const sceneColors = {
            "int-day": "#f4f0e8",
            "ext-day": "#ffe599",
            "int-night": "#6fa8dc",
            "ext-night": "#93c47d",
            "scene-unclassified": "#777"
        };
        modalContent.style.borderTop = `4px solid ${sceneColors[colorClass] || sceneColors["scene-unclassified"]}`;

        const modalGrid = document.createElement("div");
        modalGrid.className = "modal-grid-layout";

        const leftColumn = document.createElement("div");
        leftColumn.className = "modal-col-left";
        const rightColumn = document.createElement("div");
        rightColumn.className = "modal-col-right";

        const slateLine = document.createElement("div");
        slateLine.className = "modal-slate-line";

        const sceneDetails = document.createElement("div");
        const sceneNumber = document.createElement("strong");
        sceneNumber.textContent = `ESC. ${productionNumber}`;
        const sceneDescription = document.createElement("span");
        sceneDescription.textContent = [
            String(scene.location ?? "").trim(),
            String(scene.int_ext ?? "").trim(),
            String(scene.time_of_day ?? "").trim()
        ].filter(Boolean).join(" · ");
        const shootTimeStatus = document.createElement("span");
        shootTimeStatus.id = "modalShootTimeStatus";
        shootTimeStatus.className = "shoot-time-status";
        shootTimeStatus.textContent = scene.shoot_time_override
            ? ` · ${scene.shoot_time_override === "DÍA" ? "☀️" : "🌙"} Rodaje ${scene.shoot_time_override}`
            : "";
        sceneDetails.append(
            sceneNumber,
            document.createTextNode(" | "),
            sceneDescription,
            shootTimeStatus
        );

        const scheduleDetails = document.createElement("div");
        const scheduleDay = document.createElement("strong");
        scheduleDay.textContent = `DÍA ${dayNumber || "—"}`;
        const scheduleSummary = document.createElement("span");
        scheduleSummary.textContent =
            ` | ${runtimeFormatted || "—"} | ${Array.isArray(scene.shots) ? scene.shots.length : 0} planos`;
        scheduleDetails.append(scheduleDay, scheduleSummary);
        slateLine.append(sceneDetails, scheduleDetails);
        leftColumn.append(slateLine);

        const shootTimeButton = document.createElement("button");
        shootTimeButton.id = "modalShootTimeToggle";
        shootTimeButton.className = "shoot-time-toggle";
        shootTimeButton.type = "button";
        const updateShootTimeButton = () => {
            const target = getShootTimeOverrideTarget(scene);
            shootTimeButton.dataset.shootTimeTarget = target;
            shootTimeButton.textContent =
                `Grabar de ${target === "DÍA" ? "Día" : "Noche"}`;
        };
        updateShootTimeButton();
        shootTimeButton.addEventListener("click", () => {
            shootTimeButton.disabled = true;
            updateSceneShootTime(
                scene,
                shootTimeButton.dataset.shootTimeTarget
            ).finally(() => {
                shootTimeButton.disabled = false;
            });
        });
        leftColumn.append(shootTimeButton);

        const getCastItems = () => (Array.isArray(scene.breakdown_items)
            ? scene.breakdown_items
            : []
        ).filter(item =>
            ["character", "cast", "scene_cast"].includes(
                String(item.category ?? "").trim().toLowerCase()
            ) &&
            (item.state === "confirmed" || item.state === "detected")
        );
        const castLine = document.createElement("p");
        castLine.className = "modal-cast-line";
        const castHeading = document.createElement("h4");
        castHeading.textContent = "CAST";
        const updateCastLine = () => {
            castLine.replaceChildren();
            const names = getCastItems()
                .map(item => String(item.name ?? "").trim())
                .filter(Boolean);

            if (!names.length) {
                castLine.textContent = "—";
                return;
            }

            for (const name of names) {
                const pill = document.createElement("span");
                pill.className = "cast-pill";
                pill.textContent = name;
                castLine.append(pill);
            }
        };
        updateCastLine();
        leftColumn.append(castHeading, castLine);

        const shots = Array.isArray(scene.shots) ? scene.shots : [];
        const shotsHeading = document.createElement("h4");
        shotsHeading.className = "modal-shot-heading";
        shotsHeading.textContent = `SHOT LIST (${shots.length})`;
        rightColumn.append(shotsHeading);

        if (shots.length > 0) {
            const shotsTable = document.createElement("table");
            shotsTable.className = "modal-shot-table";
            const tableHead = document.createElement("thead");
            const headerRow = document.createElement("tr");
            for (const label of ["#", "Tamaño", "Ángulo", "Mov."]) {
                const header = document.createElement("th");
                header.textContent = label;
                headerRow.append(header);
            }
            tableHead.append(headerRow);
            shotsTable.append(tableHead);

            const tableBody = document.createElement("tbody");
            shots.forEach((shot, index) => {
                const row = document.createElement("tr");
                row.style.cursor = "pointer";
                row.tabIndex = 0;
                row.setAttribute("role", "button");
                row.setAttribute(
                    "aria-label",
                    `Abrir claqueta del plano ${index + 1}`
                );
                for (const value of [
                    index + 1,
                    shot.shot_type || "PM",
                    shot.camera_angle || "Normal",
                    shot.camera_movement || "Fijo"
                ]) {
                    const cell = document.createElement("td");
                    cell.textContent = String(value);
                    row.append(cell);
                }
                const openSlate = () => window.openVirtualSlate(
                    scene.production_number || scene.scene_number || scene.id,
                    index + 1,
                    shot.shot_type || "PM",
                    shot.camera_angle || "Normal",
                    shot.camera_movement || "Fijo"
                );
                row.addEventListener("click", openSlate);
                row.addEventListener("keydown", event => {
                    if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        openSlate();
                    }
                });
                tableBody.append(row);
            });
            shotsTable.append(tableBody);
            rightColumn.append(shotsTable);
        } else {
            const emptyShots = document.createElement("p");
            emptyShots.className = "modal-empty-shots";
            emptyShots.textContent = "Sin planos definidos.";
            rightColumn.append(emptyShots);
        }

        const loadingMessage = document.createElement("p");
        loadingMessage.textContent = "Cargando CAST...";
        leftColumn.append(loadingMessage);
        modalGrid.append(leftColumn, rightColumn);
        body.append(modalGrid);

        try {
            const response = await fetch(
                `/api/scenes/${encodeURIComponent(scene.id)}/breakdown`
            );
            if (!response.ok) {
                throw new Error(`Error HTTP ${response.status}`);
            }

            const breakdownItems = await response.json();
            if (body.dataset.breakdownRequestId !== String(requestId)) return;
            loadingMessage.remove();
            if (Array.isArray(breakdownItems)) {
                scene.breakdown_items = breakdownItems;
                updateCastLine();
            }
        } catch (error) {
            if (body.dataset.breakdownRequestId !== String(requestId)) return;
            loadingMessage.textContent = "No se pudo cargar el CAST.";
            console.error("Error cargando el CAST de la escena:", error);
        }
    } else {
        title.textContent = "ESCENA";
        body.textContent = "No se encontró la información de esta escena.";
    }

    sceneModalTrigger = trigger;
    overlay.setAttribute("aria-hidden", "false");
    overlay.classList.add("active");
    overlay.querySelector(".scene-modal-close").focus();
};


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


window.openVirtualSlate = function(escena, plano, tamano, angulo, movimiento) {
    const existing = document.getElementById("virtualSlateOverlay");
    if (existing) existing.remove();

    const overlay = document.createElement("div");
    overlay.id = "virtualSlateOverlay";
    overlay.className = "virtual-slate-overlay";
    overlay.setAttribute("tabindex", "0");
    overlay.setAttribute("aria-label", "Cerrar claqueta virtual");
    overlay.addEventListener("click", () => overlay.remove());
    overlay.addEventListener("keydown", event => {
        if (event.key === "Escape") {
            event.preventDefault();
            overlay.remove();
        }
    });

    const project = window.state?.project?.company_name || "PROYECTO";
    const director = window.state?.project?.director || "DIRECTOR";
    const board = document.createElement("div");
    board.className = "clapper-board";
    const sticks = document.createElement("div");
    sticks.className = "clapper-sticks";
    const grid = document.createElement("div");
    grid.className = "clapper-grid";

    const createCell = (label, value, options = {}) => {
        const cell = document.createElement("div");
        cell.className = "clapper-cell";
        if (options.flex) cell.style.flex = String(options.flex);

        const cellLabel = document.createElement("span");
        cellLabel.className = "clapper-label";
        cellLabel.textContent = label;

        const cellValue = document.createElement("span");
        cellValue.className = "clapper-value";
        cellValue.textContent = String(value ?? "");
        if (options.fontSize) cellValue.style.fontSize = options.fontSize;

        cell.append(cellLabel, cellValue);
        return cell;
    };

    const projectRow = document.createElement("div");
    projectRow.className = "clapper-row";
    projectRow.append(
        createCell("Productora", project, { flex: 1, fontSize: "24px" }),
        createCell("Director", director, { flex: 1 })
    );

    const sceneRow = document.createElement("div");
    sceneRow.className = "clapper-row";
    sceneRow.append(
        createCell("Escena", escena),
        createCell("Toma", "1"),
        createCell("Plano", plano)
    );

    const detailsRow = document.createElement("div");
    detailsRow.className = "clapper-row";
    detailsRow.append(
        createCell(
            "Encuadre",
            `${tamano || "PM"} / ${angulo || "Normal"}`,
            { flex: 2, fontSize: "20px" }
        ),
        createCell("Sonido", "Directo"),
        createCell("Movimiento", movimiento || "Fijo")
    );

    grid.append(projectRow, sceneRow, detailsRow);
    board.append(sticks, grid);
    overlay.append(board);
    document.body.append(overlay);
    overlay.focus();
};

window.openCallSheet = async function(dayNumber) {
    const scheduleData = window.lastScheduleData;
    const days = scheduleData?.best_schedule?.days;
    if (!Array.isArray(days)) return;

    const dayData = days.find(day => Number(day.day) === Number(dayNumber));
    if (!dayData) return;

    const projectId = productionProjectId ||
        document.getElementById("projectSelect")?.value;
    let csData = {};
    if (projectId) {
        try {
            const response = await fetch(
                `/api/projects/${encodeURIComponent(projectId)}/call-sheets/${encodeURIComponent(dayNumber)}`
            );
            if (response.ok) {
                csData = await response.json();
            } else {
                console.warn(
                    "No se pudieron cargar los datos del Call Sheet",
                    response.status
                );
            }
        } catch (error) {
            console.warn("No se pudieron cargar los datos del Call Sheet", error);
        }
    } else {
        console.warn("No se pudieron cargar los datos del Call Sheet: proyecto no seleccionado.");
    }

    const sceneIds = Array.isArray(dayData.scene_ids)
        ? dayData.scene_ids
        : [];
    const locations = new Map();
    const cast = new Map();
    const addUnique = (collection, value) => {
        const name = String(value ?? "").trim();
        if (name && !collection.has(name.toLocaleLowerCase())) {
            collection.set(name.toLocaleLowerCase(), name);
        }
    };

    const scenes = sceneIds
        .map(id => productionResolveScene?.(id) || productionSceneById.get(normalizeId(id)))
        .filter(Boolean);

    scenes.forEach(scene => {
        addUnique(locations, scene.location || scene.general_location);
        (Array.isArray(scene.cast) ? scene.cast : [])
            .forEach(name => addUnique(cast, name));
    });

    const runtimeSeconds = normalizeRuntime(dayData.runtime_seconds);
    const durationMins = Math.floor(runtimeSeconds / 60);
    const durationSecs = runtimeSeconds % 60;
    const timeStr = `${durationMins}m ${durationSecs}s`;
    let callSheetDate = "Por definir";
    const dateParts = typeof dayData.shoot_date === "string"
        ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(dayData.shoot_date.trim())
        : null;
    if (dateParts) {
        const [, year, month, day] = dateParts;
        const date = new Date(Number(year), Number(month) - 1, Number(day));
        if (
            date.getFullYear() === Number(year) &&
            date.getMonth() === Number(month) - 1 &&
            date.getDate() === Number(day)
        ) {
            const formattedDate = new Intl.DateTimeFormat("es", {
                weekday: "long",
                day: "numeric",
                month: "long",
            }).format(date);
            callSheetDate = formattedDate.charAt(0).toLocaleUpperCase() +
                formattedDate.slice(1);
        }
    }
    const existingModal = document.getElementById("callSheetModal");
    if (existingModal) existingModal.remove();

    const modal = document.createElement("div");
    modal.id = "callSheetModal";
    modal.className = "call-sheet-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-label", `Hoja de llamado del día ${dayNumber}`);

    const scenesTableRows = scenes.map(scene => {
        const number = scene.production_number || scene.scene_number || scene.id;
        const intExt = scene.int_ext || "";
        const timeOfDay = scene.time_of_day || "";
        const pages = (normalizeRuntime(scene.runtime_seconds) / 60).toFixed(1);
        const castText = Array.isArray(scene.cast)
            ? scene.cast.join(", ") || "-"
            : "-";
        const summary = scene.synopsis || "Sin sinopsis";
        const location = scene.location || "-";

        return `
            <tr style="border-bottom: 1px solid #ccc;">
                <td><strong>${escapeHtml(number)}</strong></td>
                <td>${escapeHtml(summary)}</td>
                <td>${escapeHtml(intExt)}</td>
                <td>${escapeHtml(timeOfDay)}</td>
                <td>${escapeHtml(pages)}</td>
                <td>${escapeHtml(castText)}</td>
                <td>${escapeHtml(location)}</td>
            </tr>
        `;
    }).join("");

    const tableHTML = `
        <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; margin-top: 15px;">
            <thead>
                <tr style="border-bottom: 2px solid #000;">
                    <th>Escena</th>
                    <th>Resumen</th>
                    <th>I/E</th>
                    <th>D/N</th>
                    <th>Pág</th>
                    <th>Elenco</th>
                    <th>Locación</th>
                </tr>
            </thead>
            <tbody>${scenesTableRows}</tbody>
        </table>
    `;

    const callSheetNotes = [
        ["Catering", csData.catering_notes],
        ["Notas técnicas", csData.tech_notes],
        ["Notas generales", csData.general_notes],
    ].filter(([, value]) => String(value ?? "").trim());

    const notesHTML = callSheetNotes.length
        ? `
            <section class="cs-logistics-notes">
                <h2>Notas de producción</h2>
                ${callSheetNotes.map(([label, value]) => `
                    <p><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</p>
                `).join("")}
            </section>
        `
        : "";

    modal.innerHTML = `
        <div class="call-sheet-content">
            <h1>HOJA DE LLAMADO - DÍA ${escapeHtml(dayNumber)}</h1>
            <div class="cs-project-info">
                <p><strong>Productora:</strong> ${escapeHtml(window.state?.project?.company_name || "Por definir")}</p>
                <p><strong>Director:</strong> ${escapeHtml(window.state?.project?.director || "Por definir")}</p>
                <p><strong>Dirección:</strong> ${escapeHtml(window.state?.project?.address || "Por definir")}</p>
            </div>
            <hr>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 12px;">
                <thead>
                    <tr style="background: #f0f0f0; text-align: center; font-weight: bold;">
                        <th style="border: 1px solid #ccc; padding: 5px;">Inicio / Término</th>
                        <th style="border: 1px solid #ccc; padding: 5px;">Listos en Set</th>
                        <th style="border: 1px solid #ccc; padding: 5px;">Clima</th>
                        <th style="border: 1px solid #ccc; padding: 5px;">Locación</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="text-align: center;">
                        <td style="border: 1px solid #ccc; padding: 5px;">
                            ${escapeHtml(csData.start_time || "08:00")} / ${escapeHtml(csData.end_time || "19:00")}
                        </td>
                        <td style="border: 1px solid #ccc; padding: 5px;">09:30</td>
                        <td style="border: 1px solid #ccc; padding: 5px;">${escapeHtml(csData.weather || "Por definir")}</td>
                        <td style="border: 1px solid #ccc; padding: 5px;">${escapeHtml([...locations.values()].join(", ") || "Por definir")}</td>
                    </tr>
                </tbody>
            </table>
            <div class="cs-header-info">
                <p><strong>Fecha:</strong> ${escapeHtml(callSheetDate)}</p>
                <p><strong>Duración estimada:</strong> ${escapeHtml(timeStr)}</p>
                <p><strong>CAST:</strong> ${escapeHtml([...cast.values()].join(", ") || "Sin asignar")}</p>
            </div>
            ${notesHTML}
            <hr>
            <h2>Escenas a rodar (${scenes.length}):</h2>
            ${tableHTML}
            <div class="cs-actions no-print">
                <button type="button" data-call-sheet-action="print">🖨️ Imprimir</button>
                <button type="button" data-call-sheet-action="close">Cerrar</button>
            </div>
        </div>
    `;

    modal.addEventListener("click", event => {
        const action = event.target instanceof Element
            ? event.target.closest("[data-call-sheet-action]")?.dataset.callSheetAction
            : null;
        if (action === "print") {
            window.print();
        } else if (action === "close") {
            modal.remove();
        }
    });
    modal.addEventListener("keydown", event => {
        if (event.key === "Escape") modal.remove();
    });
    document.body.append(modal);
    modal.querySelector('[data-call-sheet-action="close"]')?.focus();
};
