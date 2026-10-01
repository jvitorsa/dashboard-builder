const TableElement = {
  render(container, data, element, ctx) {
    container.innerHTML = "";
    const table = document.createElement("table");
    table.className = "data-table";
    // Fixed layout so a header's explicit width actually governs its column
    // (and every cell below it) instead of the browser auto-sizing to content.
    table.style.tableLayout = "fixed";

    const widths = (element.style && element.style.column_widths) || {};
    const style = element.style || {};
    const headerFont = this._fontStyleProps(style.header_font);
    const cellFont = this._fontStyleProps(style.cell_font);

    // A pivot's row-group columns keep their source names and are always
    // present; its value columns are auto-named from distinct pivot-column
    // data at query time, so the server has no way to validate/sort by them
    // ahead of running the query - only row columns are click-sortable.
    const sortableColumns =
      element.subtype === "pivot" ? new Set(element.field_mapping?.rows || []) : new Set(data.columns);
    const currentSort = (ctx && ctx.sort) || null;

    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    data.columns.forEach((c) => {
      const th = document.createElement("th");
      Object.assign(th.style, headerFont);
      // table-layout:fixed needs every column to have a real width to sum,
      // or it just divides the container's own width evenly between however
      // many columns exist - fine for 3 columns, unreadably crushed for the
      // dozens a pivot table can produce. A default (not just customized
      // widths) lets a wide table's true width exceed the container and
      // actually trigger .el-body's horizontal scrollbar instead.
      th.style.width = `${widths[c] || 120}px`;

      const label = document.createElement("span");
      label.className = "col-label";
      label.textContent = c + (currentSort?.column === c ? (currentSort.direction === "desc" ? " ▼" : " ▲") : "");
      th.appendChild(label);

      if (ctx && ctx.onSort && sortableColumns.has(c)) {
        th.classList.add("sortable");
        th.title = "Click to sort";
        th.addEventListener("click", (e) => {
          if (e.target.closest(".col-resize-handle")) return;
          const isCurrent = currentSort?.column === c;
          const nextDirection = isCurrent ? (currentSort.direction === "asc" ? "desc" : null) : "asc";
          ctx.onSort(c, nextDirection);
        });
      }

      const handle = document.createElement("span");
      handle.className = "col-resize-handle";
      handle.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const startX = e.clientX;
        const startWidth = th.offsetWidth;
        const onMove = (ev) => {
          th.style.width = `${Math.max(40, startWidth + (ev.clientX - startX))}px`;
        };
        const onUp = () => {
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
          ctx?.onColumnResize?.(c, th.offsetWidth);
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
      th.appendChild(handle);

      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    data.rows.forEach((row) => {
      const tr = document.createElement("tr");
      row.forEach((cell) => {
        const td = document.createElement("td");
        td.textContent = cell === null || cell === undefined ? "" : cell;
        Object.assign(td.style, cellFont);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);

    if (element.subtype !== "pivot" && ctx && ctx.paginated !== false) {
      const pager = document.createElement("div");
      pager.className = "table-pager";
      const page = ctx.page || 1;
      pager.innerHTML = `
        <button ${page <= 1 ? "disabled" : ""} data-dir="-1">Prev</button>
        <span>Page ${page}</span>
        <button ${data.has_more ? "" : "disabled"} data-dir="1">Next</button>
      `;
      pager.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", () => ctx.onPageChange(page + Number(btn.dataset.dir)));
      });
      container.appendChild(pager);
    }
  },

  // {family,size,color,bold,italic} -> a plain CSS-properties object for
  // Object.assign(el.style, ...) - a local copy of the same conversion
  // kpi.js/app.js/viewer.js each do their own way, since this file is
  // shared and can't depend on the host page's globals.
  _fontStyleProps(font) {
    const props = {};
    if (!font) return props;
    if (font.family) props.fontFamily = font.family;
    if (font.size) props.fontSize = `${font.size}px`;
    if (font.color) props.color = font.color;
    if (font.bold) props.fontWeight = "bold";
    if (font.italic) props.fontStyle = "italic";
    return props;
  },
};
