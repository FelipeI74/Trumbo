// --- MÓDULO DE VISTAS: PRODUCCIÓN Y CALENDARIO ---

document.addEventListener("click", event => {
  const target = event.target instanceof Element ? event.target : null;
  const tab = target?.closest(".main-nav-tab");
  if (!tab) return;

  const view = tab.dataset.view;
  const viewIds = {
    guion: "screenplayViewport",
    desglose: "productionBreakdownView",
    "plan-rodaje": "scheduleView",
    informes: "reportsView",
    produccion: "productionView",
    calendario: "calendarView",
  };
  const allViewIds = [
    "screenplayViewport",
    "productionBreakdownView",
    "scheduleView",
    "productionView",
    "calendarView",
    "reportsView",
    "characterDetailView",
  ];

  allViewIds.forEach(id => {
    const element = document.getElementById(id);
    if (element) element.hidden = true;
  });

  const selectedView = document.getElementById(viewIds[view]);
  if (selectedView) selectedView.hidden = false;

  const toolbar = document.querySelector(".editor-toolbar");
  const footer = document.querySelector(".scene-footer");
  const inspector = document.querySelector(".inspector");
  const elementSidebar = document.querySelector(".sidebar");
  const workspace = document.querySelector(".workspace");
  const isScriptView = view === "guion";
  const isInspectorView = isScriptView || view === "desglose";

  if (elementSidebar) elementSidebar.hidden = !isScriptView;
  if (workspace) {
    workspace.classList.toggle("main-view-expanded", !isScriptView);
  }
  if (toolbar) toolbar.hidden = !isScriptView;
  if (footer) footer.hidden = !isScriptView;
  if (inspector) inspector.hidden = !isInspectorView;

  if (view === "produccion" && typeof window.initProductionBoard === "function") {
    window.initProductionBoard();
  }
  if (view === "calendario" && typeof window.initCalendar === "function") {
    window.initCalendar();
  }
});
