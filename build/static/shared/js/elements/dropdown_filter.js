// Single delegated listener for every multiselect dropdown on the page,
// registered once - avoids leaking a new document-level listener on every
// re-render (renderGrid() recreates element DOM nodes on tab-switch/add/delete).
// The panel itself is reparented to <body> (see render() below), so each
// panel stops its own clicks from bubbling here - any click that does reach
// this listener is a genuine outside click.
document.addEventListener("click", () => {
  document.querySelectorAll(".ms-panel:not(.hidden)").forEach((panel) => panel.classList.add("hidden"));
});

const DropdownFilterElement = {
  render(container, optionsData, element, ctx) {
    // The multiselect panel (built below) is floated to <body> as
    // position:fixed so it can escape this element's own canvas-item/
    // viewer-element overflow:hidden and render above whatever sits below
    // it, instead of being clipped by its own container. container.innerHTML
    // = "" below only tears down what's still inside `container` - a panel
    // from this element's previous render already lives under <body>, so it
    // would otherwise leak as an orphaned node on every refresh.
    document.querySelectorAll(".ms-panel").forEach((p) => {
      if (p.dataset.msOwner === element.id) p.remove();
    });

    container.innerHTML = "";
    const values = optionsData.values || [];
    const selected = (ctx && ctx.selectedValues) || [];

    if (element.subtype === "single") {
      const select = document.createElement("select");
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "(all)";
      select.appendChild(blank);
      values.forEach((v) => {
        const opt = document.createElement("option");
        opt.value = v;
        opt.textContent = v;
        if (selected[0] === v) opt.selected = true;
        select.appendChild(opt);
      });
      select.addEventListener("change", () => {
        ctx.onChange(select.value ? [select.value] : []);
      });
      container.appendChild(select);
      return;
    }

    // Multiselect: a closed-by-default dropdown button that opens a
    // checkbox panel, rather than an always-expanded list of checkboxes.
    const wrap = document.createElement("div");
    wrap.className = "ms-dropdown";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "ms-toggle";

    const panel = document.createElement("div");
    panel.className = "ms-panel hidden";
    panel.dataset.msOwner = element.id;
    panel.addEventListener("click", (e) => e.stopPropagation());

    function updateToggleLabel() {
      toggle.textContent = selected.length ? `${selected.length} selected` : "(all)";
    }

    values.forEach((v) => {
      const label = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = v;
      cb.checked = selected.includes(v);
      cb.addEventListener("change", () => {
        const checked = Array.from(panel.querySelectorAll("input:checked")).map((i) => i.value);
        selected.length = 0;
        selected.push(...checked);
        updateToggleLabel();
        ctx.onChange(checked);
      });
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + v));
      panel.appendChild(label);
    });

    toggle.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!panel.classList.contains("hidden")) {
        panel.classList.add("hidden");
        return;
      }
      document.querySelectorAll(".ms-panel").forEach((p) => p.classList.add("hidden"));
      const rect = toggle.getBoundingClientRect();
      panel.style.left = `${rect.left}px`;
      panel.style.top = `${rect.bottom + 4}px`;
      panel.style.width = `${rect.width}px`;
      panel.classList.remove("hidden");
    });

    updateToggleLabel();
    wrap.appendChild(toggle);
    container.appendChild(wrap);
    document.body.appendChild(panel);
  },

  // A re-render of the same element's container (see the top of render())
  // cleans up its own previously-floated panel, but a deleted element's
  // render() never runs again - the builder calls this on delete so that
  // panel doesn't leak under <body> forever (mirrors ChartElement.destroy).
  destroy(elementId) {
    document.querySelectorAll(".ms-panel").forEach((p) => {
      if (p.dataset.msOwner === elementId) p.remove();
    });
  },
};
