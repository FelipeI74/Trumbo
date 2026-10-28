// --- MÓDULO DE PRODUCCIÓN (STRIPBOARD) ---

async function initProductionBoard() {
    const root = document.getElementById("stripboard-root");
    if (!root) return;

    // 1. Crear la estructura base del tablero
    root.innerHTML = `
        <div class="stripboard-container">
            <div class="stripboard-pool" id="stripboard-pool">
                <h2>Escenas sin asignar</h2>
                <div id="pool-cards"></div>
            </div>
            <div class="stripboard-days" id="stripboard-days"></div>
        </div>
    `;

    try {
        const projectId = document.getElementById("projectSelect").value;
        if (!projectId) return;

        // 2. Obtener las escenas desde el endpoint que ya usa ADÜMN
        const response = await fetch(`/api/projects/${projectId}/scheduling-input`);
        const data = await response.json();
        
        // 3. Pintar las tarjetas y los días
        renderStripboard(data.scenes || []);

    } catch (error) {
        console.error("Error cargando el tablero de producción:", error);
        root.innerHTML = `<p style="padding: 20px; color: #F14646;">Error al cargar los datos del tablero. Revisa la consola.</p>`;
    }
}

function renderStripboard(scenes) {
    const poolCards = document.getElementById("pool-cards");
    const daysContainer = document.getElementById("stripboard-days");

    if (!poolCards || !daysContainer) return;

    // --- RENDERIZAR LAS TARJETAS (POOL) ---
    poolCards.innerHTML = scenes.map(scene => {
        const intExt = (scene.int_ext || "").toUpperCase();
        const time = (scene.time_of_day || "").toUpperCase();
        
        // Determinar el color de la tarjeta según la industria
        let colorClass = "int-day"; // Por defecto
        if (intExt.includes("EXT") && time.includes("NOCHE")) {
            colorClass = "ext-night";
        } else if (intExt.includes("EXT") && (time.includes("DIA") || time.includes("DÍA"))) {
            colorClass = "ext-day";
        } else if (intExt.includes("INT") && time.includes("NOCHE")) {
            colorClass = "int-night";
        }

        return `
            <div class="strip-card ${colorClass}" draggable="true" data-scene-id="${scene.scene_id}">
                <div class="strip-card-header">ESC. ${scene.production_number || scene.scene_number}</div>
                <div class="strip-card-body">${scene.location || "Sin locación"} - ${intExt} ${time}</div>
            </div>
        `;
    }).join("");

    // --- RENDERIZAR LOS DÍAS (VACÍOS POR AHORA) ---
    // Creamos 5 columnas de días de ejemplo para ver el layout
    daysContainer.innerHTML = Array.from({ length: 5 }, (_, i) => `
        <div class="strip-day">
            <div class="strip-day-header">
                <span>Día ${i + 1}</span>
            </div>
            <div class="strip-day-stats">0 escenas | 0.00 pág</div>
        </div>
    `).join("");
}

// Exponer la función para que app.js pueda llamarla
window.initProductionBoard = initProductionBoard;