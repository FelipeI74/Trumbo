// --- MÓDULO DE VISTAS: PRODUCCIÓN Y CALENDARIO ---

document.addEventListener("click", (event) => {
  const tab = event.target.closest(".main-nav-tab");
  if (!tab) return;

  const view = tab.dataset.view;

  // 1. SIEMPRE, al hacer clic en cualquier pestaña, limpiamos las vistas nuevas
  // para que no se queden "pegadas" encima de las otras.
  const prodView = document.getElementById("productionView");
  const calView = document.getElementById("calendarView");
  
  if (prodView) prodView.hidden = true;
  if (calView) calView.hidden = true;

  // 2. Si el clic fue en "guion", restauramos el editor clásico
  if (view === "guion") {
    document.getElementById("screenplayViewport").hidden = false;
    document.querySelector(".editor-toolbar").hidden = false;
    document.querySelector(".scene-footer").hidden = false;
    return; // Terminamos aquí para no ocultar el editor
  }

  // 3. Si el clic fue en "produccion" o "calendario", las mostramos
  if (view === "produccion" || view === "calendario") {
    
    // Ocultar las vistas clásicas (desglose, plan, informes)
    document.getElementById("screenplayViewport").hidden = true;
    document.getElementById("productionBreakdownView").hidden = true;
    document.getElementById("scheduleView").hidden = true;
    document.getElementById("reportsView").hidden = true;
    document.getElementById("characterDetailView").hidden = true;
    
    // Ocultar toolbar y footer
    document.querySelector(".editor-toolbar").hidden = true;
    document.querySelector(".scene-footer").hidden = true;

    // Mostrar la vista que corresponda
    if (view === "produccion") {
      if (prodView) prodView.hidden = false;
      if (typeof window.initProductionBoard === "function") {
        window.initProductionBoard();
      }
    }

    if (view === "calendario") {
      if (calView) calView.hidden = false;
      if (typeof window.initCalendar === "function") {
        window.initCalendar();
      }
    }
  }
});