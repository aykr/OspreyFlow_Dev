// The Labels control (ADR-076): the analyst chooses, for each type of node now in view, which of its
// properties names it on the canvas. The choice is kept in this browser only and nothing is sent to
// the server, so it is a way of looking, not a change to the case.
import { useEffect, useId, useRef, useState } from "react";

import type { EntityTypeDef } from "../../../../packages/schemas/generated";
import { getLabelChoices, labelPropertiesFor, onLabelChoicesChange, setLabelChoice } from "./labelChoices";

export interface LabelsMenuProps {
  /** The ontology's entity types, which say which properties each can be labelled by. */
  entityTypes: readonly EntityTypeDef[];
  /** The names of the types that have a node in view now; a type not in view is not offered. Asked
   * for only while the panel is open, so a large view is not scanned on every redraw. */
  getTypesInView: () => readonly string[];
}

const DEFAULT_VALUE = "";

export function LabelsMenu({ entityTypes, getTypesInView }: LabelsMenuProps) {
  const [open, setOpen] = useState(false);
  const [, bump] = useState(0);
  const button = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  // A choice made here, or in another tab of this browser, redraws the pickers.
  useEffect(() => onLabelChoicesChange(() => bump((n) => n + 1)), []);

  const choices = getLabelChoices();
  const typesInView = open ? getTypesInView() : [];
  const inView = new Set(typesInView);
  const types = entityTypes
    .filter((type) => inView.has(type.name))
    .sort((a, b) => a.name.localeCompare(b.name, "en-GB"));
  // A type in view that the ontology does not describe cannot be offered, but is not silent.
  const unknown = typesInView.filter((name) => !entityTypes.some((type) => type.name === name));

  return (
    <div
      style={{
        // Placed, with the Icons control beside it, by `GlassCanvas`.
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-4)",
        alignItems: "flex-start",
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.stopPropagation();
          setOpen(false);
          button.current?.focus();
        }
      }}
    >
      <button
        ref={button}
        type="button"
        className="radial-menu__item"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        title="Choose which property names each type of node"
        onClick={() => setOpen((v) => !v)}
      >
        Labels
      </button>
      {open && (
        <div
          id={panelId}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-4)",
            padding: "var(--sp-8)",
            background: "var(--surface-raised)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          {types.length === 0 && unknown.length === 0 ? <span>No nodes in view to label.</span> : null}
          {types.map((type) => {
            const properties = labelPropertiesFor(type);
            if (properties.length === 0) return <span key={type.name}>{`${type.name}: no property to choose from.`}</span>;
            const chosen = choices[type.name];
            return (
              <label key={type.name} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
                <span style={{ minWidth: "8ch" }}>{type.name}</span>
                <select
                  aria-label={`Label for ${type.name}`}
                  value={chosen !== undefined && properties.includes(chosen) ? chosen : DEFAULT_VALUE}
                  onChange={(event) =>
                    setLabelChoice(type.name, event.target.value === DEFAULT_VALUE ? null : event.target.value)
                  }
                >
                  <option value={DEFAULT_VALUE}>Default</option>
                  {properties.map((property) => (
                    <option key={property} value={property}>
                      {property}
                    </option>
                  ))}
                </select>
              </label>
            );
          })}
          <span style={{ color: "var(--text-secondary)" }}>
            Kept in this browser only; it does not change the case.
          </span>
        </div>
      )}
    </div>
  );
}
