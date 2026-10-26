// ADR-127 decision 5, Amendment 10 (unit B2-5b): the control that names a recipe's `deduplicate` key.
//
// The author lists the source columns that identify a row, in order (the order is part of the key),
// and may pass a column through a Knowledge Adapter, from the same catalogue Map offers. A second run
// into the same case then skips every row whose key it already holds. It sits in Connect beside the
// source's other declarations (`09_INGEST_STUDIO.md` is silent on where it is authored; the key names
// source columns and Connect's PATCH carries it), and Connect reads no source, so a column is typed
// as the columns that carry the marking are, and the server checks it against the source on save.
//
// A binding the control does not author (a several-column transform, a literal) is kept as it is: it
// can be moved and removed here, and its columns are Map's to change.
import { useState } from "react";

import type { FieldBinding, TransformDescriptor } from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives/Button";
import { Input } from "../design/primitives/Input";
import { Select } from "../design/primitives/Select";

/** A binding with its unset entries dropped, so what is sent back is what the author set. */
export function cleanBinding(binding: FieldBinding): FieldBinding {
  return Object.fromEntries(
    Object.entries(binding).filter(([, value]) => value !== null && value !== undefined),
  ) as FieldBinding;
}

/** The one source column a binding is keyed on, or null for one the control does not edit. */
export function singleColumn(binding: FieldBinding): string | null {
  if (binding.literal !== undefined && binding.literal !== null) return null;
  if (binding.map) return null;
  if (binding.fields && binding.fields.length > 0) return null;
  return binding.field ?? null;
}

/** A binding in words, for the ones the control does not edit. */
export function describeBinding(binding: FieldBinding): string {
  const column = singleColumn(binding);
  if (column !== null) return column;
  const transform = binding.transform ? ` (${binding.transform})` : "";
  if (binding.fields && binding.fields.length > 0) return `${binding.fields.join(" + ")}${transform}`;
  if (binding.literal !== undefined && binding.literal !== null) return `the fixed value ${String(binding.literal)}`;
  if (binding.map) return `${binding.field ?? "a column"}, through a value map`;
  return "(empty)";
}

export function moveKeyPart(parts: FieldBinding[], index: number, by: -1 | 1): FieldBinding[] {
  const target = index + by;
  if (target < 0 || target >= parts.length) return parts;
  const next = [...parts];
  const moved = next[index]!;
  next[index] = next[target]!;
  next[target] = moved;
  return next;
}

/** The transforms a one-column key part may take: those of one column, a structured one once per
 * part (as Map offers them), never bare. */
export function oneColumnTransforms(transforms: TransformDescriptor[]): { value: string; label: string }[] {
  return transforms
    .filter((t) => t.arity <= 1)
    .flatMap((t) =>
      (t.parts ?? []).length > 0
        ? (t.parts ?? []).map((part) => ({ value: `${t.name}(part=${part})`, label: `${t.name} — ${part}` }))
        : [{ value: t.name, label: t.name }],
    );
}

export interface DeduplicateControlProps {
  keyParts: FieldBinding[];
  onChange: (next: FieldBinding[]) => void;
  transforms: TransformDescriptor[];
  /** The draft is a further version of a recipe already published: a changed key then refuses
   * later runs into a case holding rows kept under the old one, which the author is told. */
  newVersion?: boolean;
}

export function DeduplicateControl({ keyParts, onChange, transforms, newVersion = false }: DeduplicateControlProps) {
  const [draftColumn, setDraftColumn] = useState("");
  const [repeated, setRepeated] = useState<string | null>(null);
  const options = oneColumnTransforms(transforms);

  function addColumn() {
    const name = draftColumn.trim();
    if (!name) return;
    if (keyParts.some((part) => singleColumn(part) === name)) {
      // Said, not ignored; the box keeps what was typed so the author sees what was refused.
      setRepeated(name);
      return;
    }
    setDraftColumn("");
    setRepeated(null);
    onChange([...keyParts, { field: name }]);
  }

  function setTransform(index: number, transform: string) {
    onChange(
      keyParts.map((part, i) => {
        if (i !== index) return part;
        const next: FieldBinding = { ...part };
        if (transform) next.transform = transform;
        else delete next.transform;
        return next;
      }),
    );
  }

  return (
    <fieldset style={{ border: "none", padding: 0, marginBottom: "var(--sp-16)" }}>
      <legend>Skip rows this case has already loaded</legend>
      <p style={{ margin: "0 0 var(--sp-8)", color: "var(--text-tertiary)" }}>
        Name the columns that identify a row, in order. A second run into the same case skips every row it
        has already loaded. A row with an empty key column is never skipped.
      </p>
      {keyParts.length > 0 ? (
        <ol aria-label="Key columns" style={{ margin: "0 0 var(--sp-8)", paddingLeft: "var(--sp-24)" }}>
          {keyParts.map((part, index) => {
            const column = singleColumn(part);
            const name = describeBinding(part);
            return (
              <li key={`${index}:${name}`} data-column={column ?? undefined}>
                <span style={{ display: "inline-flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}>
                  <span>{name}</span>
                  {column !== null ? (
                    <Select
                      aria-label={`Transform for ${column}`}
                      value={part.transform ?? ""}
                      onChange={(e) => setTransform(index, e.target.value)}
                    >
                      <option value="">No transform</option>
                      {options.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </Select>
                  ) : null}
                  <Button
                    aria-label={`Move ${name} up`}
                    disabled={index === 0}
                    onClick={() => onChange(moveKeyPart(keyParts, index, -1))}
                  >
                    Up
                  </Button>
                  <Button
                    aria-label={`Move ${name} down`}
                    disabled={index === keyParts.length - 1}
                    onClick={() => onChange(moveKeyPart(keyParts, index, 1))}
                  >
                    Down
                  </Button>
                  <Button
                    aria-label={`Remove ${name} from the key`}
                    onClick={() => onChange(keyParts.filter((_, i) => i !== index))}
                  >
                    Remove
                  </Button>
                </span>
              </li>
            );
          })}
        </ol>
      ) : null}
      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
        <Input
          aria-label="Key column name"
          value={draftColumn}
          onChange={(e) => {
            setDraftColumn(e.target.value);
            setRepeated(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addColumn();
            }
          }}
          placeholder="Column name (e.g. payer)"
        />
        <Button onClick={addColumn}>Add key column</Button>
        {keyParts.length > 0 ? <Button onClick={() => onChange([])}>Clear the key</Button> : null}
      </div>
      {repeated !== null ? (
        <p role="status" style={{ margin: "var(--sp-8) 0 0", color: "var(--warning)" }}>
          {repeated} is already in the key
        </p>
      ) : null}
      {newVersion ? (
        <p style={{ margin: "var(--sp-8) 0 0", color: "var(--text-tertiary)" }}>
          Changing the key will refuse later runs into a case that already holds rows loaded under the old
          key, until those loads are reverted.
        </p>
      ) : null}
    </fieldset>
  );
}
