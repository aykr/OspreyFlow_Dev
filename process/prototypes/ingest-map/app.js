// Throwaway prototype — no framework, no build step, on purpose. It reads
// data.json (produced by generate_data.py from the REAL headless recipe
// engine and the REAL CDR fixture) and renders roughly the three-pane
// layout sketched in 09_INGEST_STUDIO.md §4. Interaction shortcuts taken
// here (click-to-select only, no drag-to-bind, no editing) are exactly
// the kind of thing ADR-018 marks as free to change after review.

let DATA = null;
let rowIndex = 0;
let selected = null; // {kind: 'entity'|'edge', ref or type}

function bindingLabel(binding) {
  if (binding.literal !== null && binding.literal !== undefined) {
    return `literal: ${JSON.stringify(binding.literal)}`;
  }
  if (binding.fields) {
    const t = binding.transform ? `${binding.transform}(${binding.fields.join(", ")})` : binding.fields.join(", ");
    return t;
  }
  let expr = binding.field ?? "";
  if (binding.transform) expr = `${binding.transform}(${expr})`;
  if (binding.map) expr = `map(${expr})`;
  return expr;
}

function currentRow() {
  return DATA.rows.find((r) => r.row_index === rowIndex) ?? null;
}

function renderSourceFields() {
  const row = currentRow();
  const raw = row ? row.raw : {};
  const unmapped = new Set(DATA.unmapped_fields.map((f) => f.field));
  const el = document.getElementById("fieldList");
  el.innerHTML = "";
  for (const col of DATA.source_columns) {
    const div = document.createElement("div");
    div.className = "field" + (unmapped.has(col) ? " unmapped" : "");
    div.innerHTML = `<div class="name">${col}</div><div class="val">${raw[col] ?? ""}</div>`;
    el.appendChild(div);
  }
}

function renderTemplate() {
  const row = currentRow();
  const body = document.getElementById("templateBody");
  body.innerHTML = "";

  const status = document.createElement("div");
  status.innerHTML = `<span class="row-status ${row.status}">${row.status}</span>`;
  if (row.status === "duplicate") {
    status.innerHTML += ` <span class="empty-hint">collapses into row ${row.duplicate_of}</span>`;
  }
  if (row.status === "rejected") {
    status.innerHTML += `<div class="reason">${row.reason}</div>`;
  }
  body.appendChild(status);

  if (row.status !== "loaded") return;

  const entitiesByRef = {};
  for (const e of row.entities) entitiesByRef[e.ref] = e;

  const graph = document.createElement("div");
  graph.className = "graph";

  const nodeEl = (ref) => {
    const templateDef = DATA.recipe.entities.find((e) => e.ref === ref);
    const resolved = entitiesByRef[ref];
    const div = document.createElement("div");
    div.className = "node" + (selected && selected.kind === "entity" && selected.ref === ref ? " selected" : "");
    const props = resolved
      ? Object.entries(resolved.properties)
          .slice(0, 3)
          .map(([k, v]) => `<div class="prop"><b>${k}</b>: ${v}</div>`)
          .join("")
      : "";
    div.innerHTML = `<div class="ref">${ref}</div><div class="type">${templateDef.type}</div>${props}`;
    div.onclick = () => {
      selected = { kind: "entity", ref };
      render();
    };
    return div;
  };

  if (row.edges.length === 0) {
    for (const e of row.entities) graph.appendChild(nodeEl(e.ref));
  } else {
    for (const edgeDef of row.edges) {
      graph.appendChild(nodeEl(edgeDef.from));
      const edgeWrap = document.createElement("div");
      edgeWrap.className = "edge";
      const isSelected = selected && selected.kind === "edge" && selected.type === edgeDef.type;
      edgeWrap.innerHTML = `<span class="arrow">→</span><span class="label${isSelected ? " selected" : ""}">${edgeDef.type}</span>`;
      edgeWrap.querySelector(".label").onclick = () => {
        selected = { kind: "edge", type: edgeDef.type };
        render();
      };
      graph.appendChild(edgeWrap);
      graph.appendChild(nodeEl(edgeDef.to));
    }
  }
  body.appendChild(graph);
}

function renderInspector() {
  const el = document.getElementById("inspectorBody");
  if (!selected) {
    el.innerHTML = '<p class="empty-hint">Select an entity or edge.</p>';
    return;
  }
  const row = currentRow();

  if (selected.kind === "entity") {
    const def = DATA.recipe.entities.find((e) => e.ref === selected.ref);
    const resolved = row.status === "loaded" ? row.entities.find((e) => e.ref === selected.ref) : null;
    el.innerHTML = `
      <div class="kv">
        <div>POLE class</div><div>${def.pole_class}</div>
        <div>Type</div><div>${def.type}</div>
        <div>Match on</div><div>${def.match_on ?? "—"}</div>
        <div>On match</div><div>${def.on_match}</div>
      </div>
      <h2>Bindings</h2>
      <ul class="binding-list">
        ${Object.entries(def.properties)
          .map(([name, b]) => `<li><span class="bname">${name}</span><br><span class="bexpr">${bindingLabel(b)}</span></li>`)
          .join("")}
      </ul>
      ${resolved ? `<h2>Resolved (this row)</h2><pre>${JSON.stringify(resolved.properties, null, 2)}</pre>` : ""}
    `;
  } else {
    const def = DATA.recipe.edges.find((e) => e.type === selected.type);
    const resolved = row.status === "loaded" ? row.edges.find((e) => e.type === selected.type) : null;
    el.innerHTML = `
      <div class="kv">
        <div>Type</div><div>${def.type}</div>
        <div>From</div><div>${def.from}</div>
        <div>To</div><div>${def.to}</div>
        ${def.temporal ? `<div>Temporal</div><div>${bindingLabel(def.temporal.at)}</div>` : ""}
      </div>
      <h2>Bindings</h2>
      <ul class="binding-list">
        ${Object.entries(def.properties)
          .map(([name, b]) => `<li><span class="bname">${name}</span><br><span class="bexpr">${bindingLabel(b)}</span></li>`)
          .join("")}
      </ul>
      ${resolved ? `<h2>Resolved (this row)</h2><pre>${JSON.stringify({ ...resolved.properties, instant: resolved.instant }, null, 2)}</pre>` : ""}
    `;
  }
}

function renderPager() {
  document.getElementById("rowLabel").textContent = `Row ${rowIndex + 1} of ${DATA.rows.length} sample`;
  document.getElementById("prevRow").disabled = rowIndex === 0;
  document.getElementById("nextRow").disabled = rowIndex === DATA.rows.length - 1;
  const s = DATA.summary;
  document.getElementById("summaryLabel").textContent =
    `${s.rows_read} read · ${s.rows_deduplicated} deduplicated · ${s.rejections} rejected`;
}

function render() {
  renderSourceFields();
  renderTemplate();
  renderInspector();
  renderPager();
}

async function main() {
  const res = await fetch("data.json");
  DATA = await res.json();
  document.getElementById("recipeMeta").textContent =
    `${DATA.recipe.label} — recipe v${DATA.recipe.version}, ontology v${DATA.recipe.ontology_version}`;
  rowIndex = DATA.rows[0].row_index;
  render();

  document.getElementById("prevRow").onclick = () => {
    const idx = DATA.rows.findIndex((r) => r.row_index === rowIndex);
    if (idx > 0) {
      rowIndex = DATA.rows[idx - 1].row_index;
      selected = null;
      render();
    }
  };
  document.getElementById("nextRow").onclick = () => {
    const idx = DATA.rows.findIndex((r) => r.row_index === rowIndex);
    if (idx < DATA.rows.length - 1) {
      rowIndex = DATA.rows[idx + 1].row_index;
      selected = null;
      render();
    }
  };
}

main();
