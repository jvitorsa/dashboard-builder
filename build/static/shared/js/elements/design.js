// Pure design elements (shape, text) - no query/data, so unlike every other
// renderer here their render() takes no `data` argument and is synchronous.

const ShapeElement = {
  render(container, element) {
    container.innerHTML = "";
    const style = element.style || {};
    const shape = document.createElement("div");
    shape.style.width = "100%";
    shape.style.height = "100%";
    shape.style.boxSizing = "border-box";
    shape.style.backgroundColor = style.fill_color || "#2a78d6";
    const borderWidth = style.border_width ?? 1;
    shape.style.border = borderWidth > 0 ? `${borderWidth}px solid ${style.border_color || "#1c5cab"}` : "none";
    if (element.subtype === "circle") shape.style.borderRadius = "50%";
    container.appendChild(shape);
  },
};

// kpi.js already declares a same-purpose VALIGN_TO_JUSTIFY as a global -
// both files load as plain scripts in the same scope, so this needs its own
// name to avoid a duplicate-const SyntaxError.
const TEXT_VALIGN_TO_JUSTIFY = { top: "flex-start", middle: "center", bottom: "flex-end" };

const TextElement = {
  render(container, element) {
    container.innerHTML = "";
    const style = element.style || {};
    const box = document.createElement("div");
    box.style.width = "100%";
    box.style.height = "100%";
    box.style.boxSizing = "border-box";
    box.style.display = "flex";
    box.style.flexDirection = "column";
    box.style.justifyContent = TEXT_VALIGN_TO_JUSTIFY[style.valign] || "flex-start";
    box.style.textAlign = style.align || "left";
    box.style.whiteSpace = "pre-wrap";
    box.style.overflowWrap = "break-word";
    box.style.overflow = "auto";
    if (style.background_color) box.style.backgroundColor = style.background_color;
    const font = style.font || {};
    if (font.family) box.style.fontFamily = font.family;
    if (font.size) box.style.fontSize = `${font.size}px`;
    if (font.color) box.style.color = font.color;
    if (font.bold) box.style.fontWeight = "bold";
    if (font.italic) box.style.fontStyle = "italic";
    box.textContent = style.text_content || "";
    container.appendChild(box);
  },
};
