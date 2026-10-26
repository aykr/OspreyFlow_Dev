// The entities of the row template, as a list a keyboard can use (ADR-127 Amendment 13's second gap,
// rule 13). The Map canvas is mouse-only, and "+ entity" selects only the entity it has just made, so
// an entity already in the template could not be chosen, and none of its controls (ref, type, match,
// bindings, content, handling, delete) reached, without a pointer. Each entity is a button here, with
// the keys the link list has (`listKeys`); the canvas path is unchanged and ends in the same selection.
//
// Every entity is listed (a cut would hide from the keyboard what the canvas still draws, rule 2); a
// long list scrolls in its own region.
import type { RecipeEntity } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { moveFocusInList } from "./listKeys";

export interface EntityListProps {
  entities: RecipeEntity[];
  /** The ref of the entity open in the inspector, if one is. */
  selectedRef: string | null;
  onSelect: (ref: string) => void;
}

export function EntityList({ entities, selectedRef, onSelect }: EntityListProps) {
  if (entities.length === 0) {
    return <p style={{ margin: 0, padding: "0 var(--sp-8)", color: "var(--text-tertiary)" }}>No entities yet.</p>;
  }
  return (
    <ul
      aria-label="Entities"
      onKeyDown={moveFocusInList}
      style={{
        listStyle: "none",
        margin: 0,
        padding: "0 var(--sp-8)",
        maxHeight: 120,
        overflowY: "auto",
        display: "grid",
        gap: "var(--sp-4)",
      }}
    >
      {entities.map((entity, index) => (
        <li key={entity.ref}>
          <Button
            aria-label={`Entity ${index + 1}: ${entity.ref} (${entity.type})`}
            aria-pressed={entity.ref === selectedRef}
            variant={entity.ref === selectedRef ? "primary" : "default"}
            onClick={() => onSelect(entity.ref)}
            style={{ width: "100%", textAlign: "left" }}
          >
            {`${entity.ref} (${entity.type})`}
          </Button>
        </li>
      ))}
    </ul>
  );
}
