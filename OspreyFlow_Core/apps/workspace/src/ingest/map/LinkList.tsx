// The links of the row template, as a list a keyboard can use, with a form that makes one
// (ADR-127 Amendment 13's recorded gap, rule 13). The Map canvas is mouse-only: a link is picked on it
// by a click, and made by "+ link" and two more clicks, so no link control in Map could be reached
// without a pointer. Here each link is a button (Tab reaches it, Enter or Space chooses it, the arrow
// keys, Home and End move between them), and a link is made by choosing its two ends and its type
// with selects. The canvas path is unchanged; both end in the same selection.
//
// A template holds a few dozen links at most, so every one is listed (a cut would hide a link from
// the keyboard that the canvas still draws, rule 2); a long list scrolls in its own region.
import { useState } from "react";

import type { OntologySchema, RecipeEdge, RowTemplate } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Select } from "../../design/primitives/Select";
import { moveFocusInList } from "./listKeys";
import { edgeTypesForEndpoints, findEntity } from "./rowTemplate";

export interface LinkListProps {
  template: RowTemplate;
  ontology: OntologySchema;
  /** The index in `template.edges` of the link open in the inspector, if one is. */
  selectedIndex: number | null;
  onSelect: (index: number) => void;
  /** A link between two entities of the template, of a type the ontology allows between them. */
  onAdd: (from: string, to: string, type: string) => void;
}

function labelOf(edge: RecipeEdge, index: number): string {
  return `Link ${index + 1}: ${edge.type}, ${edge.from} to ${edge.to}`;
}

export function LinkList({ template, ontology, selectedIndex, onSelect, onAdd }: LinkListProps) {
  const edges = template.edges ?? [];
  const entities = template.entities;
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);
  const [type, setType] = useState<string | null>(null);

  // The ends shown are the chosen ones while the template still holds them, and the first two
  // otherwise (an entity removed since was chosen no longer).
  const fromRef = entities.some((e) => e.ref === from) ? from! : (entities[0]?.ref ?? "");
  const toRef = entities.some((e) => e.ref === to) ? to! : (entities[1]?.ref ?? "");
  const fromEntity = findEntity(template, fromRef);
  const toEntity = findEntity(template, toRef);
  const sameEnd = fromRef !== "" && fromRef === toRef;
  const types =
    fromEntity && toEntity && !sameEnd
      ? edgeTypesForEndpoints(ontology, fromEntity.type, toEntity.type)
      : [];
  const typeName = types.some((t) => t.name === type) ? type! : (types[0]?.name ?? "");

  return (
    <section aria-label="Links of the row template" style={{ display: "grid", gap: "var(--sp-8)", padding: "0 var(--sp-8)" }}>
      {edges.length > 0 ? (
        <ul
          aria-label="Links"
          onKeyDown={moveFocusInList}
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            maxHeight: 120,
            overflowY: "auto",
            display: "grid",
            gap: "var(--sp-4)",
          }}
        >
          {edges.map((edge, index) => (
            <li key={index}>
              <Button
                aria-label={labelOf(edge, index)}
                aria-pressed={index === selectedIndex}
                variant={index === selectedIndex ? "primary" : "default"}
                onClick={() => onSelect(index)}
                style={{ width: "100%", textAlign: "left" }}
              >
                {`${edge.type}: ${edge.from} → ${edge.to}`}
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p style={{ margin: 0, color: "var(--text-tertiary)" }}>No links yet.</p>
      )}

      {entities.length < 2 ? (
        <p style={{ margin: 0, color: "var(--text-tertiary)" }}>
          Add two entities to join them with a link.
        </p>
      ) : (
        <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}>
          <Select aria-label="From entity" value={fromRef} onChange={(e) => setFrom(e.target.value)}>
            {entities.map((entity) => (
              <option key={entity.ref} value={entity.ref}>
                {`${entity.ref} (${entity.type})`}
              </option>
            ))}
          </Select>
          <Select aria-label="To entity" value={toRef} onChange={(e) => setTo(e.target.value)}>
            {entities.map((entity) => (
              <option key={entity.ref} value={entity.ref}>
                {`${entity.ref} (${entity.type})`}
              </option>
            ))}
          </Select>
          <Select aria-label="Link type" value={typeName} onChange={(e) => setType(e.target.value)}>
            {types.map((t) => (
              <option key={t.name} value={t.name}>
                {t.name}
              </option>
            ))}
          </Select>
          <Button disabled={typeName === ""} onClick={() => onAdd(fromRef, toRef, typeName)}>
            Add link
          </Button>
          {sameEnd ? (
            <span role="status" style={{ color: "var(--warning)" }}>
              A link joins two different entities.
            </span>
          ) : types.length === 0 ? (
            <span role="status" style={{ color: "var(--warning)" }}>
              No ontology link type connects these two entity types.
            </span>
          ) : null}
        </div>
      )}
    </section>
  );
}
