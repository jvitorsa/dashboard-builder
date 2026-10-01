const Api = (() => {
  async function req(method, path, body) {
    const resp = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const errBody = await resp.json();
        // AppError puts the human-readable message in `error`; the catch-all
        // handler for unexpected exceptions puts it in `details` instead
        // (`error` is just "internal_error" there) - prefer whichever is present.
        detail = errBody.error === "internal_error" ? errBody.details || detail : errBody.error || detail;
      } catch (e) {}
      throw new Error(`${method} ${path} failed: ${detail}`);
    }
    if (resp.status === 204) return null;
    return resp.json();
  }

  return {
    getVersion: () => req("GET", "/api/version"),
    listDataSources: () => req("GET", "/api/datasources"),
    getDataSourceSchema: (filename) => req("GET", `/api/datasources/${encodeURIComponent(filename)}/schema`),
    listQueries: () => req("GET", "/api/queries"),
    getQuerySchema: (path) => req("GET", `/api/queries/schema?path=${encodeURIComponent(path)}`),

    listDashboards: () => req("GET", "/api/dashboards"),
    getDashboard: (id) => req("GET", `/api/dashboards/${encodeURIComponent(id)}`),
    createDashboard: (data) => req("POST", "/api/dashboards", data),
    updateDashboard: (id, data) => req("PUT", `/api/dashboards/${encodeURIComponent(id)}`, data),
    deleteDashboard: (id) => req("DELETE", `/api/dashboards/${encodeURIComponent(id)}`),
    duplicateDashboard: (id, newName) => req("POST", `/api/dashboards/${encodeURIComponent(id)}/duplicate`, { new_name: newName }),
    exportDashboard: (id) => req("POST", `/api/dashboards/${encodeURIComponent(id)}/export`),

    // sort: {column, direction} | null | undefined - undefined (the default)
    // omits the key entirely so the server falls back to the element's own
    // configured default_sort; null explicitly requests no sort, overriding it.
    getElementData: (dashboardId, elementId, activeFilters, page, pageSize, sort, showAll) =>
      req("POST", "/api/data/element", {
        dashboard_id: dashboardId,
        element_id: elementId,
        active_filters: activeFilters || [],
        page: page || 1,
        page_size: pageSize || undefined,
        ...(sort !== undefined ? { sort } : {}),
        ...(showAll ? { show_all: true } : {}),
      }),
    getFilterOptions: (dashboardId, filterElementId) =>
      req("POST", "/api/data/filter-options", { dashboard_id: dashboardId, filter_element_id: filterElementId }),
  };
})();
