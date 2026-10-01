// Read-only dashboard viewer. Renders a saved dashboard JSON (built with the
// builder at build/builder.py) and keeps it live via filters + polling - no
// editing, dragging, or config here.

const RENDERERS = {
  chart: ChartElement,
  table: TableElement,
  card: KpiElement,
  drop_filter: DropdownFilterElement,
  shape: ShapeElement,
  text: TextElement,
};

let currentDashboard = null;
let activeTabId = null;
let elementStates = {};
let dataVersion = null;

function getActiveTab() {
  return currentDashboard.tabs.find((t) => t.id === activeTabId);
}

function targetsOf(tab, filterElement) {
  const direct = new Set(filterElement.filter.targets.elements || []);
  (filterElement.filter.targets.groups || []).forEach((gid) => {
    const group = tab.groups.find((g) => g.id === gid);
    if (group) group.element_ids.forEach((id) => direct.add(id));
  });
  return direct;
}

function buildActiveFiltersPayload(tab) {
  return tab.elements
    .filter((e) => e.type === "drop_filter" && elementStates[e.id]?.values?.length)
    .map((e) => ({ filter_element_id: e.id, values: elementStates[e.id].values }));
}

async function refreshElement(element) {
  const tab = getActiveTab();
  const container = document.getElementById(`body-${element.id}`);
  if (!container) return;

  try {
    if (element.type === "drop_filter") {
      const options = await Api.getFilterOptions(currentDashboard.id, element.id);
      elementStates[element.id] = elementStates[element.id] || { values: element.filter.default_value || [] };
      RENDERERS.drop_filter.render(container, options, element, {
        selectedValues: elementStates[element.id].values,
        onChange: async (values) => {
          elementStates[element.id].values = values;
          const targets = targetsOf(tab, element);
          await Promise.all(tab.elements.filter((e) => targets.has(e.id)).map((e) => refreshElement(e)));
        },
      });
      return;
    }

    if (element.type === "shape" || element.type === "text") {
      RENDERERS[element.type].render(container, element);
      return;
    }

    const state = (elementStates[element.id] = elementStates[element.id] || { page: 1 });
    const activeFilters = buildActiveFiltersPayload(tab);
    const showAll =
      element.type === "table" && element.subtype !== "pivot" && element.field_mapping?.pagination_mode === "show_all";
    const data = await Api.getElementData(currentDashboard.id, element.id, activeFilters, state.page, undefined, state.sort, showAll);
    RENDERERS[element.type].render(container, data, element, {
      page: state.page,
      paginated: !showAll,
      // state.sort is undefined until the user clicks a header - fall back
      // to the element's own configured default_sort for the initial
      // render/indicator so it reflects what the server actually applied.
      sort: state.sort !== undefined ? state.sort : element.field_mapping?.default_sort || null,
      onPageChange: (newPage) => {
        state.page = Math.max(1, newPage);
        refreshElement(element);
      },
      onSort: (column, direction) => {
        state.sort = direction ? { column, direction } : null;
        state.page = 1;
        refreshElement(element);
      },
    });
  } catch (e) {
    container.innerHTML = `<div class="empty-hint">${e.message}</div>`;
  }
}

async function refreshAllElements() {
  const tab = getActiveTab();
  if (!tab) return;
  const filters = tab.elements.filter((e) => e.type === "drop_filter");
  const others = tab.elements.filter((e) => e.type !== "drop_filter");
  await Promise.all(filters.map(refreshElement));
  await Promise.all(others.map(refreshElement));
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function defaultElementTitle(element) {
  const tab = getActiveTab();
  const group = element.group_id ? tab?.groups.find((g) => g.id === element.group_id) : null;
  const suffix = group ? ` · ${group.name}` : "";
  if (element.type === "drop_filter") return `Filter: ${element.filter.dimension || "(unset)"}${suffix}`;
  return `${element.type}${element.subtype ? " / " + element.subtype : ""}${suffix}`;
}

// Mirrors app.js's elementTitle - element.style.title can hide the header
// entirely or override its text (see the builder's config panel).
function elementTitle(element) {
  const t = element.style?.title;
  if (t?.show === false) return "";
  if (t?.text) return t.text;
  return defaultElementTitle(element);
}

function fontStyleCss(font) {
  if (!font) return "";
  const parts = [];
  if (font.family) parts.push(`font-family:${font.family}`);
  if (font.size) parts.push(`font-size:${font.size}px`);
  if (font.color) parts.push(`color:${font.color}`);
  if (font.bold) parts.push("font-weight:bold");
  if (font.italic) parts.push("font-style:italic");
  return parts.join(";");
}

// Mirrors app.js's paddingCss.
function paddingCss(element) {
  const v = element.style?.padding_v;
  const h = element.style?.padding_h;
  if ((v === undefined || v === null || v === "") && (h === undefined || h === null || h === "")) return "";
  return `${v ?? 8}px ${h ?? 10}px`;
}

// Mirrors app.js's headerClasses.
function headerClasses(element) {
  const separatorOff = element.style?.header_separator === false;
  const titleEmpty = !elementTitle(element);
  let cls = "";
  if (separatorOff) cls += " no-separator";
  if (separatorOff && titleEmpty) cls += " header-collapsed";
  return cls;
}

// Mirrors app.js's migrateLayoutIfNeeded - a dashboard that has never been
// reopened in the builder since free positioning replaced the grid could
// still be in grid-cell units when viewed here.
function migrateLayoutIfNeeded(dashboard) {
  if (dashboard.settings.canvas_width) return;
  const columns = dashboard.settings.grid_columns || 12;
  const rowHeight = dashboard.settings.row_height_px || 40;
  const width = 1200;
  const cellWidth = width / columns;
  dashboard.tabs.forEach((tab) => {
    tab.elements.forEach((element) => {
      const l = element.layout;
      element.layout = {
        x: Math.round(l.x * cellWidth),
        y: Math.round(l.y * rowHeight),
        w: Math.round(l.w * cellWidth),
        h: Math.round(l.h * rowHeight),
      };
    });
  });
  dashboard.settings.canvas_width = width;
}

function renderGrid() {
  const gridEl = document.getElementById("viewer-grid");
  gridEl.innerHTML = "";
  gridEl.style.position = "relative";
  gridEl.style.width = `${currentDashboard.settings.canvas_width || 1200}px`;

  const tab = getActiveTab();
  if (!tab) return;

  const maxBottom = tab.elements.reduce((max, el) => Math.max(max, el.layout.y + el.layout.h), 0);
  gridEl.style.minHeight = `${maxBottom}px`;

  tab.elements.forEach((element) => {
    const wrap = document.createElement("div");
    wrap.className = `viewer-element${element.style?.background === false ? " no-background" : ""}`;
    wrap.style.position = "absolute";
    wrap.style.left = `${element.layout.x}px`;
    wrap.style.top = `${element.layout.y}px`;
    wrap.style.width = `${element.layout.w}px`;
    wrap.style.height = `${element.layout.h}px`;
    if (element.style?.background !== false && element.style?.background_color) wrap.style.backgroundColor = element.style.background_color;
    const group = element.group_id ? tab.groups.find((g) => g.id === element.group_id) : null;
    if (group?.color) wrap.style.borderLeft = `4px solid ${group.color}`;
    const titleFontCss = fontStyleCss(element.style?.title?.font);
    const pad = paddingCss(element);
    const bodyStyleAttr = pad ? ` style="padding:${pad}"` : "";
    wrap.innerHTML = `<div class="el-header${headerClasses(element)}"><span${titleFontCss ? ` style="${titleFontCss}"` : ""}>${escapeHtml(elementTitle(element))}</span></div><div class="el-body" id="body-${element.id}"${bodyStyleAttr}></div>`;
    gridEl.appendChild(wrap);
  });

  refreshAllElements();
}

function renderTabsBar() {
  const bar = document.getElementById("tabs-bar");
  bar.innerHTML = "";
  currentDashboard.tabs.forEach((tab) => {
    const btn = document.createElement("button");
    btn.textContent = tab.name;
    if (tab.id === activeTabId) btn.classList.add("active");
    btn.addEventListener("click", () => {
      activeTabId = tab.id;
      renderTabsBar();
      renderGrid();
    });
    bar.appendChild(btn);
  });
}

const BUILDER_PORT = 5050; // matches config.BUILDER_PORT's default - override both if you change one

function updateEditLink() {
  const link = document.getElementById("edit-link");
  const builderOrigin = `${location.protocol}//${location.hostname}:${BUILDER_PORT}`;
  link.href = currentDashboard ? `${builderOrigin}/?id=${encodeURIComponent(currentDashboard.id)}` : builderOrigin;
}

async function loadDashboard(id) {
  currentDashboard = await Api.getDashboard(id);
  activeTabId = currentDashboard.tabs[0]?.id;
  elementStates = {};
  migrateLayoutIfNeeded(currentDashboard);
  document.getElementById("dashboard-title").textContent = currentDashboard.name;
  document.getElementById("dashboard-picker").value = currentDashboard.id;
  updateEditLink();
  renderTabsBar();
  renderGrid();
}

async function init() {
  const { dashboards } = await Api.listDashboards();
  const picker = document.getElementById("dashboard-picker");

  if (!dashboards.length) {
    document.getElementById("empty-state").classList.remove("hidden");
    updateEditLink();
    return;
  }

  picker.innerHTML = dashboards.map((d) => `<option value="${d.id}">${d.name}</option>`).join("");
  picker.addEventListener("change", () => loadDashboard(picker.value));

  const requestedId = new URLSearchParams(location.search).get("id");
  const sorted = [...dashboards].sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
  const initialId = (requestedId && dashboards.some((d) => d.id === requestedId)) ? requestedId : sorted[0].id;
  await loadDashboard(initialId);

  setInterval(async () => {
    try {
      const { data_version } = await Api.getVersion();
      if (dataVersion !== null && data_version !== dataVersion) await refreshAllElements();
      dataVersion = data_version;
    } catch (e) {
      // ignore transient poll failures
    }
  }, 4000);
}

document.addEventListener("DOMContentLoaded", init);
