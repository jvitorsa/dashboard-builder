const VALIGN_TO_JUSTIFY = { top: "flex-start", middle: "center", bottom: "flex-end" };

const KpiElement = {
  render(container, data, element) {
    container.innerHTML = "";
    const metrics = (element.field_mapping && element.field_mapping.metrics) || [];
    if (!data.rows.length || !metrics.length) {
      container.style.display = "";
      container.style.justifyContent = "";
      container.innerHTML = '<div class="empty-hint">No metric configured</div>';
      return;
    }
    const style = element.style || {};
    // Row (left/center/right) alignment is plain text-align; column
    // (top/middle/bottom) alignment needs the container to be a flex column
    // so justify-content can position the metric group(s) within its height.
    container.style.textAlign = style.align || "left";
    container.style.display = "flex";
    container.style.flexDirection = "column";
    container.style.justifyContent = VALIGN_TO_JUSTIFY[style.valign] || "flex-start";
    const metricFontCss = this._fontCss(style.metric_font);
    const labelFontCss = this._fontCss(style.label_font);

    // Label placement relative to the value - "bottom" (default) and "top"
    // stack in a column, "left"/"right" sit side by side; the CSS class picks
    // the flex direction, DOM order picks which side the label lands on.
    const labelPosition = ["top", "bottom", "left", "right"].includes(style.label_position) ? style.label_position : "bottom";
    const labelFirst = labelPosition === "top" || labelPosition === "left";

    const row = data.rows[0];
    metrics.forEach((m) => {
      const idx = data.columns.indexOf(m.alias);
      const value = idx >= 0 ? row[idx] : null;
      const wrap = document.createElement("div");
      wrap.className = `kpi-metric kpi-label-${labelPosition}`;
      const valueHtml = `<div class="kpi-value"${metricFontCss ? ` style="${metricFontCss}"` : ""}>${formatNumber(value)}</div>`;
      const labelHtml =
        m.show_label === false
          ? ""
          : `<div class="kpi-label"${labelFontCss ? ` style="${labelFontCss}"` : ""}>${this._escapeHtml(m.alias)}</div>`;
      wrap.innerHTML = labelFirst ? labelHtml + valueHtml : valueHtml + labelHtml;
      container.appendChild(wrap);
    });
  },

  _fontCss(font) {
    if (!font) return "";
    const parts = [];
    if (font.family) parts.push(`font-family:${font.family}`);
    if (font.size) parts.push(`font-size:${font.size}px`);
    if (font.color) parts.push(`color:${font.color}`);
    if (font.bold) parts.push("font-weight:bold");
    if (font.italic) parts.push("font-style:italic");
    return parts.join(";");
  },

  _escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  },
};

function formatNumber(value) {
  if (value === null || value === undefined) return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
