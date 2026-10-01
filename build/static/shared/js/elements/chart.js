// Fixed-order categorical palette (dataviz default, light surface) - assigned
// by series/slice index, never cycled/reassigned as selections change.
const DEFAULT_SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];

// Sequential single-hue (blue) ramp defaults, light -> dark, for map magnitude
// encoding (choropleth region value, point-heatmap density) - never a rainbow
// scale. User-overridable per element via style.gradient_low_color/_high_color;
// ECharts' visualMap interpolates continuously across just the two endpoints.
const DEFAULT_GRADIENT_LOW = "#cde2fb";
const DEFAULT_GRADIENT_HIGH = "#0d366b";

const SYMBOL_SHAPES = { circle: "circle", square: "rect", triangle: "triangle", diamond: "diamond", none: "none" };

function seriesColor(m, i) {
  return (m && m.color) || DEFAULT_SERIES_COLORS[i % DEFAULT_SERIES_COLORS.length];
}

function valueRange(values) {
  const clean = values.filter((v) => v !== null && v !== undefined && !Number.isNaN(Number(v)));
  if (!clean.length) return { min: 0, max: 1 };
  return { min: Math.min(...clean), max: Math.max(...clean) };
}

function gradientColors(element) {
  return [
    element.style?.gradient_low_color || DEFAULT_GRADIENT_LOW,
    element.style?.gradient_high_color || DEFAULT_GRADIENT_HIGH,
  ];
}

// Point-heatmap rendering knobs - defaults match the original hardcoded
// values, so an element with none of these set looks exactly as before.
// blurSize is the usual culprit behind a "blurry"-looking heatmap: it's a
// gaussian blur radius that bleeds each point's color into its neighbors.
function heatmapStyle(element) {
  const s = element.style || {};
  return {
    pointSize: s.heatmap_point_size ?? 14,
    blurSize: s.heatmap_blur_size ?? 18,
    minOpacity: s.heatmap_min_opacity ?? 0,
    maxOpacity: s.heatmap_max_opacity ?? 1,
  };
}

// Saved pan/zoom (style.map_center/map_zoom, written back by the georoam
// capture in _wireMapRoamCapture) so a dragged-into-place map keeps its
// framing across re-renders instead of recentering on every setOption call.
function mapView(element) {
  const s = element.style || {};
  const view = {};
  if (s.map_center) view.center = s.map_center;
  if (s.map_zoom !== undefined && s.map_zoom !== null) view.zoom = s.map_zoom;
  return view;
}

// {family,size,color,bold,italic} -> ECharts axisLabel textStyle keys (not a
// CSS string - axisLabel wants separate fontFamily/fontSize/fontWeight/etc).
function axisLabelStyle(font) {
  if (!font) return {};
  const style = {};
  if (font.family) style.fontFamily = font.family;
  if (font.size) style.fontSize = font.size;
  if (font.color) style.color = font.color;
  if (font.bold) style.fontWeight = "bold";
  if (font.italic) style.fontStyle = "italic";
  return style;
}

// {decimals, thousands, prefix, suffix} applied to a value-axis tick label.
function formatAxisNumber(value, fmt) {
  if (value === null || value === undefined || value === "") return value;
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  const opts = {};
  if (fmt?.decimals !== undefined && fmt?.decimals !== null && fmt.decimals !== "") {
    opts.minimumFractionDigits = fmt.decimals;
    opts.maximumFractionDigits = fmt.decimals;
  }
  if (fmt?.thousands === false) opts.useGrouping = false;
  return `${fmt?.prefix || ""}${num.toLocaleString(undefined, opts)}${fmt?.suffix || ""}`;
}

const ChartElement = {
  _instances: new Map(),
  _geoCache: new Map(), // scope -> Promise<registered echarts map name>

  async render(container, data, element, ctx) {
    try {
      let chart = this._instances.get(element.id);
      if (!chart || chart.getDom() !== container.firstChild) {
        container.innerHTML = "";
        const div = document.createElement("div");
        div.style.width = "100%";
        div.style.height = "100%";
        container.appendChild(div);
        chart = echarts.init(div);
        this._instances.set(element.id, chart);
      }

      if (element.subtype === "map") await this._renderMap(chart, data, element, ctx);
      else if (element.subtype === "pie") this._renderPie(chart, data, element);
      else this._renderCartesian(chart, data, element);

      chart.resize();
    } catch (e) {
      this.destroy(element.id);
      container.innerHTML = `<div class="empty-hint">${e.message}</div>`;
    }
  },

  // Covers line/bar/scatter/combined/area/stacked_bar - all share the same
  // dimension + metrics data shape, differing only in per-series ECharts
  // series type and styling.
  _renderCartesian(chart, data, element) {
    const dimension = element.field_mapping.dimension;
    const metrics = element.field_mapping.metrics || [];
    const dimIdx = data.columns.indexOf(dimension);
    const categories = data.rows.map((r) => r[dimIdx]);

    const usesRightAxis = metrics.some((m) => m.axis === "right");
    const isStackedBar = element.subtype === "stacked_bar";

    const series = metrics.map((m, i) => {
      const idx = data.columns.indexOf(m.alias);
      const color = seriesColor(m, i);
      const logicalType =
        element.subtype === "combined"
          ? m.render_as || "bar"
          : element.subtype === "scatter"
          ? "scatter"
          : isStackedBar
          ? "bar"
          : element.subtype === "area"
          ? "area"
          : element.subtype || "bar";
      const isArea = logicalType === "area";

      const s = {
        name: m.alias,
        type: isArea ? "line" : logicalType,
        yAxisIndex: usesRightAxis && m.axis === "right" ? 1 : 0,
        data: data.rows.map((r) => r[idx]),
      };
      if (isStackedBar) s.stack = "total";
      if (s.type === "bar") {
        s.itemStyle = { color };
      } else if (s.type === "line") {
        s.lineStyle = { color };
        s.symbol = SYMBOL_SHAPES[m.point_shape] || "circle";
        s.symbolSize = m.point_shape === "none" ? 0 : 8;
        s.itemStyle = { color: m.point_color || color };
        if (isArea) s.areaStyle = { color, opacity: 0.35 };
      } else if (s.type === "scatter") {
        s.symbol = SYMBOL_SHAPES[m.point_shape] || "circle";
        s.itemStyle = { color: m.point_color || color };
      }
      return s;
    });

    const axisFont = axisLabelStyle(element.style?.axis_font);
    const numFmt = element.style?.axis_number_format;
    const makeValueAxis = (name) => ({
      type: "value",
      name: name || undefined,
      nameLocation: "middle",
      nameGap: 50,
      axisLabel: { ...axisFont, formatter: (v) => formatAxisNumber(v, numFmt) },
    });
    const chartArea = element.style?.chart_area;

    chart.setOption(
      {
        tooltip: { trigger: "axis" },
        legend: { show: series.length > 1 },
        xAxis: {
          type: "category",
          data: categories,
          name: element.style?.x_axis_name || undefined,
          nameLocation: "middle",
          nameGap: 28,
          axisLabel: axisFont,
        },
        yAxis: usesRightAxis
          ? [makeValueAxis(element.style?.y_axis_name), makeValueAxis(element.style?.y_axis_name_right)]
          : makeValueAxis(element.style?.y_axis_name),
        series,
        // An axis name needs extra room beyond the tick labels it sits below/
        // beside, or it gets clipped by the container - only widen the
        // default margins for that (the user's own chart_area, from the
        // plot-area drag handles, is left exactly as they set it).
        grid: chartArea || {
          left: 40 + (element.style?.y_axis_name ? 20 : 0),
          right: (usesRightAxis ? 40 : 16) + (element.style?.y_axis_name_right ? 20 : 0),
          top: series.length > 1 ? 30 : 10,
          bottom: 30 + (element.style?.x_axis_name ? 20 : 0),
        },
      },
      true
    );
  },

  // Single value metric sliced by the dimension column - slice colors follow
  // the fixed categorical order, same as every other chart type.
  _renderPie(chart, data, element) {
    const dimension = element.field_mapping.dimension;
    const metrics = element.field_mapping.metrics || [];
    const m = metrics[0];
    const dimIdx = data.columns.indexOf(dimension);
    const valIdx = m ? data.columns.indexOf(m.alias) : -1;

    const pieData = data.rows.map((r, i) => ({
      name: r[dimIdx],
      value: valIdx >= 0 ? r[valIdx] : null,
      itemStyle: { color: DEFAULT_SERIES_COLORS[i % DEFAULT_SERIES_COLORS.length] },
    }));

    chart.setOption(
      {
        tooltip: { trigger: "item" },
        legend: { show: pieData.length > 1, bottom: 0, type: "scroll" },
        series: [
          {
            type: "pie",
            radius: "65%",
            center: ["50%", "48%"],
            data: pieData,
            label: { show: pieData.length <= 8 },
          },
        ],
      },
      true
    );
  },

  // Fetches + registers a GeoJSON atlas once per scope, cached across every
  // map element on the page (vendored locally - this tool is offline-only).
  // Resolves to {name, nameLookup} - nameLookup maps an upper-cased region
  // name to the GeoJSON's own canonical casing, since a user's source data
  // ("PARAÍBA") rarely matches a map atlas's display casing ("Paraíba")
  // exactly, and ECharts' region match is a plain case-sensitive string key.
  _loadGeo(scope) {
    const name =
      scope === "us_states" ? "usa" : scope === "brazil_states" ? "brazil" : scope === "south_america" ? "south_america" : "world";
    if (!this._geoCache.has(name)) {
      const promise = fetch(`/static/shared/js/vendor/geo/${name}.json`)
        .then((r) => r.json())
        .then((geoJson) => {
          echarts.registerMap(name, geoJson);
          const nameLookup = new Map();
          (geoJson.features || []).forEach((f) => {
            const n = f.properties && f.properties.name;
            if (n) nameLookup.set(String(n).toUpperCase(), n);
          });
          return { name, nameLookup };
        });
      this._geoCache.set(name, promise);
    }
    return this._geoCache.get(name);
  },

  // field_mapping.map_mode: "region" (choropleth over field_mapping.dimension,
  // scoped to world/us_states/brazil_states) or "point_heatmap" (lat/lng
  // point density, backend aliases the chosen columns to "lat"/"lng").
  async _renderMap(chart, data, element, ctx) {
    const mode = element.field_mapping.map_mode || "region";
    const scope = element.field_mapping.map_scope || "world";
    const metrics = element.field_mapping.metrics || [];
    const m = metrics[0];
    const { name: mapName, nameLookup } = await this._loadGeo(scope);
    const view = mapView(element);

    if (mode === "point_heatmap") {
      const latIdx = data.columns.indexOf("lat");
      const lngIdx = data.columns.indexOf("lng");
      const valIdx = m ? data.columns.indexOf(m.alias) : -1;
      const points = data.rows.map((r) => [r[lngIdx], r[latIdx], valIdx >= 0 ? r[valIdx] : 1]);
      const { min, max } = valueRange(points.map((p) => p[2]));
      const hm = heatmapStyle(element);

      chart.setOption(
        {
          tooltip: {},
          geo: { map: mapName, roam: true, ...view, itemStyle: { areaColor: "#f3f3f1", borderColor: "#d9d8d2" } },
          visualMap: { min, max, calculable: true, inRange: { color: gradientColors(element) }, bottom: 4, left: 4 },
          series: [
            {
              type: "heatmap",
              coordinateSystem: "geo",
              data: points,
              pointSize: hm.pointSize,
              blurSize: hm.blurSize,
              minOpacity: hm.minOpacity,
              maxOpacity: hm.maxOpacity,
            },
          ],
        },
        true
      );
      this._wireMapRoamCapture(chart, "geo", ctx);
      return;
    }

    const dimension = element.field_mapping.dimension;
    const dimIdx = data.columns.indexOf(dimension);
    const valIdx = m ? data.columns.indexOf(m.alias) : -1;
    const regionData = data.rows.map((r) => {
      const raw = r[dimIdx];
      const matched = raw !== null && raw !== undefined ? nameLookup.get(String(raw).toUpperCase()) : undefined;
      return { name: matched || raw, value: valIdx >= 0 ? r[valIdx] : null };
    });
    const { min, max } = valueRange(regionData.map((d) => d.value));

    chart.setOption(
      {
        tooltip: { trigger: "item" },
        visualMap: { min, max, calculable: true, inRange: { color: gradientColors(element) }, bottom: 4, left: 4 },
        series: [
          {
            type: "map",
            map: mapName,
            roam: true,
            ...view,
            data: regionData,
            itemStyle: { areaColor: "#f3f3f1", borderColor: "#d9d8d2" },
            emphasis: { itemStyle: { areaColor: "#eda100" } },
          },
        ],
      },
      true
    );
    this._wireMapRoamCapture(chart, "series", ctx);
  },

  // Captures the post-drag/zoom center+zoom (debounced, since "georoam"
  // fires continuously mid-gesture) and reports it to ctx.onMapViewChange so
  // the caller can persist it - without this, every unrelated live-apply
  // re-render calls chart.setOption(..., true) and silently resets any
  // manual pan/zoom the user just did. Re-wired on every render (off() first)
  // since setOption doesn't recreate the chart instance or its listeners.
  _wireMapRoamCapture(chart, source, ctx) {
    chart.off("georoam");
    if (!ctx || typeof ctx.onMapViewChange !== "function") return;
    chart.on("georoam", () => {
      clearTimeout(chart._mapRoamDebounce);
      chart._mapRoamDebounce = setTimeout(() => {
        const opt = chart.getOption();
        const cfg = source === "geo" ? opt.geo && opt.geo[0] : opt.series && opt.series[0];
        if (cfg && cfg.center) ctx.onMapViewChange({ center: cfg.center, zoom: cfg.zoom });
      }, 400);
    });
  },

  resize(elementId) {
    const chart = this._instances.get(elementId);
    if (chart) chart.resize();
  },

  destroy(elementId) {
    const chart = this._instances.get(elementId);
    if (chart) {
      clearTimeout(chart._mapRoamDebounce);
      chart.dispose();
      this._instances.delete(elementId);
    }
  },
};
