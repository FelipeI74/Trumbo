// --- MÓDULO DE CALENDARIO ---

async function initCalendar() {
    const root = document.getElementById("calendarView");
    if (!root) return;

    const projectId = document.getElementById("projectSelect").value;
    if (!projectId) return;

    // 1. Cargar la configuración existente
    try {
        const response = await fetch(`/api/projects/${projectId}/calendar`);
        const data = await response.json();

        if (data.start_date) document.getElementById("calendarStartDate").value = data.start_date;
        if (data.day_type) document.getElementById("calendarDayType").value = data.day_type;
        
        // Marcar los checkboxes de días laborables
        const workDays = (data.work_days || "1,2,3,4,5").split(",");
        document.querySelectorAll(".work-day").forEach(cb => {
            cb.checked = workDays.includes(cb.value);
        });

        // Si no hay fecha guardada, ponemos la de hoy por defecto
        const dateInput = document.getElementById("calendarStartDate");
        if (dateInput && !dateInput.value) {
            const today = new Date();
            const yyyy = today.getFullYear();
            const mm = String(today.getMonth() + 1).padStart(2, '0');
            const dd = String(today.getDate()).padStart(2, '0');
            dateInput.value = `${yyyy}-${mm}-${dd}`;
        }

    } catch (error) {
        console.error("Error cargando el calendario:", error);
    }

    // 2. Guardar la configuración
    const saveBtn = document.getElementById("saveCalendarButton");
    if (saveBtn) {
        // Evitar que se agreguen múltiples eventos si se llama varias veces
        saveBtn.replaceWith(saveBtn.cloneNode(true));
        const newSaveBtn = document.getElementById("saveCalendarButton");
        
        newSaveBtn.addEventListener("click", async () => {
            const startDate = document.getElementById("calendarStartDate").value;
            const dayType = document.getElementById("calendarDayType").value;
            const workDays = [...document.querySelectorAll(".work-day:checked")].map(cb => cb.value).join(",");

            try {
                await fetch(`/api/projects/${projectId}/calendar`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        start_date: startDate || null,
                        work_days: workDays || "1,2,3,4,5",
                        day_type: dayType,
                    }),
                });
                alert("✅ Calendario guardado correctamente.");
            } catch (error) {
                console.error("Error guardando el calendario:", error);
                alert("❌ Error al guardar el calendario.");
            }
        });
    }
}

// Exponer la función para app.js
window.initCalendar = initCalendar;
