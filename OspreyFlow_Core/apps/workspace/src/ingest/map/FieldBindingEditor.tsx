// One property's `FieldBinding` — `spec/09_INGEST_STUDIO.md` §4: field vs.
// `fields` (multi-column, arity from the transform catalogue) vs. `literal`
// vs. `map`, never a free expression.
import { useState } from "react";
import type { DragEvent } from "react";

import type { FieldBinding, TransformDescriptor } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Checkbox } from "../../design/primitives/Checkbox";
import { Input } from "../../design/primitives/Input";
import { Select } from "../../design/primitives/Select";
import { arityForTransform } from "./rowTemplate";

export interface FieldBindingEditorProps {
  binding: FieldBinding;
  sourceFieldNames: string[];
  transforms: TransformDescriptor[];
  onChange: (binding: FieldBinding) => void;
  onRemove?: () => void;
  /** ADR-127 Amendment 15: offer "optional" (leave the property out when its cell is empty). Only
   * a property's binding has a property to leave out: a time binding does not. */
  allowOptional?: boolean;
}

type Kind = "field" | "literal" | "map";

function kindOf(binding: FieldBinding): Kind {
  if (binding.literal !== undefined && binding.literal !== null) return "literal";
  if (binding.map) return "map";
  return "field";
}

export function FieldBindingEditor({
  binding,
  sourceFieldNames,
  transforms,
  onChange,
  onRemove,
  allowOptional = false,
}: FieldBindingEditorProps) {
  const kind = kindOf(binding);
  const arity = arityForTransform(transforms, binding.transform);
  const fields = binding.fields ?? (binding.field ? [binding.field] : []);

  function setKind(next: Kind) {
    if (next === "literal") onChange({ literal: "" });
    else if (next === "map") onChange({ field: binding.field ?? sourceFieldNames[0], map: {} });
    else onChange({ field: sourceFieldNames[0] });
  }

  const keptOptional = binding.optional ? { optional: true } : {};

  function setTransform(name: string) {
    const nextArity = arityForTransform(transforms, name || null);
    if (nextArity > 1) {
      const nextFields = Array.from({ length: nextArity }, (_, i) => fields[i] ?? sourceFieldNames[0] ?? "");
      onChange({ fields: nextFields, transform: name || undefined, ...keptOptional });
    } else {
      onChange({
        field: fields[0] ?? sourceFieldNames[0] ?? "",
        transform: name || undefined,
        ...keptOptional,
      });
    }
  }

  function setFieldAt(index: number, value: string) {
    if (arity > 1) {
      const nextFields = [...fields];
      nextFields[index] = value;
      onChange({ ...binding, field: undefined, fields: nextFields });
    } else {
      onChange({ ...binding, field: value, fields: undefined });
    }
  }

  function handleDrop(e: DragEvent) {
    const dropped = e.dataTransfer.getData("text/x-osprey-field");
    if (!dropped || !sourceFieldNames.includes(dropped)) return;
    e.preventDefault();
    setFieldAt(0, dropped);
  }

  return (
    <div
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
      style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4, 4px)" }}
    >
      <div style={{ display: "flex", gap: "var(--sp-4, 4px)", alignItems: "center" }}>
        <Select aria-label="Binding kind" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
          <option value="field">Field</option>
          <option value="literal">Literal</option>
          <option value="map">Value map</option>
        </Select>
        {onRemove && (
          <Button onClick={onRemove} aria-label="Remove property">
            ✕
          </Button>
        )}
      </div>

      {kind === "literal" && (
        <Input
          aria-label="Literal value"
          value={typeof binding.literal === "string" ? binding.literal : String(binding.literal ?? "")}
          onChange={(e) => onChange({ literal: e.target.value })}
          placeholder="Literal value"
        />
      )}

      {(kind === "field" || kind === "map") && (
        <>
          <div style={{ display: "flex", gap: "var(--sp-4, 4px)", flexWrap: "wrap" }}>
            {Array.from({ length: Math.max(arity, 1) }, (_, i) => (
              <Select
                key={i}
                aria-label={arity > 1 ? `Source column ${i + 1}` : "Source column"}
                value={fields[i] ?? ""}
                onChange={(e) => setFieldAt(i, e.target.value)}
              >
                <option value="" disabled>
                  {arity > 1 ? `column ${i + 1} of ${arity}` : "choose a field"}
                </option>
                {sourceFieldNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </Select>
            ))}
          </div>
          <Select
            aria-label="Transform"
            value={binding.transform ?? ""}
            onChange={(e) => setTransform(e.target.value)}
          >
            <option value="">No transform</option>
            {/* ADR-104: a structured transform is offered once per part, never bare. */}
            {transforms.flatMap((t) =>
              (t.parts ?? []).length > 0
                ? (t.parts ?? []).map((part) => (
                    <option key={`${t.name}:${part}`} value={`${t.name}(part=${part})`}>
                      {`${t.name} — ${part}`}
                    </option>
                  ))
                : [
                    <option key={t.name} value={t.name}>
                      {t.name}
                      {t.arity > 1 ? ` (${t.arity} columns)` : ""}
                    </option>,
                  ],
            )}
          </Select>
        </>
      )}

      {allowOptional && kind !== "literal" && (
        <label style={{ display: "flex", alignItems: "center", gap: "var(--sp-4, 4px)" }}>
          <Checkbox
            checked={binding.optional === true}
            onChange={(e) => {
              const next = { ...binding };
              if (e.target.checked) next.optional = true;
              else delete next.optional;
              onChange(next);
            }}
          />
          Optional: leave the property out when its cell is empty
        </label>
      )}

      {kind === "map" && (
        <ValueMapEditor
          map={binding.map ?? {}}
          onChange={(map) => onChange({ ...binding, map })}
        />
      )}
    </div>
  );
}

function ValueMapEditor({
  map,
  onChange,
}: {
  map: Record<string, string>;
  onChange: (map: Record<string, string>) => void;
}) {
  // Rows are editing state, not the canonical Record: a Record cannot hold two
  // rows with the same key, so while one is empty or mid-edit the rows live
  // here and only their collapsed form is published. Re-reading the prop would
  // discard those rows on our own echo, so resync only when the published map
  // no longer matches what the rows collapse to (a different draft loaded).
  const [entries, setEntries] = useState<[string, string][]>(() => Object.entries(map));
  if (JSON.stringify(map) !== JSON.stringify(Object.fromEntries(entries))) {
    setEntries(Object.entries(map));
  }

  function publish(next: [string, string][]) {
    setEntries(next);
    onChange(Object.fromEntries(next));
  }

  function setEntry(index: number, key: string, value: string) {
    const next: [string, string][] = [...entries];
    next[index] = [key, value];
    publish(next);
  }

  function addEntry() {
    publish([...entries, ["", ""]]);
  }

  function removeEntry(index: number) {
    publish(entries.filter((_, i) => i !== index));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4, 4px)" }}>
      {entries.map(([key, value], i) => (
        <div key={i} style={{ display: "flex", gap: "var(--sp-4, 4px)" }}>
          <Input
            value={key}
            placeholder="source value"
            onChange={(e) => setEntry(i, e.target.value, value)}
          />
          <span>→</span>
          <Input
            value={value}
            placeholder="mapped value"
            onChange={(e) => setEntry(i, key, e.target.value)}
          />
          <Button onClick={() => removeEntry(i)} aria-label="Remove mapping">
            ✕
          </Button>
        </div>
      ))}
      <Button onClick={addEntry}>+ mapping</Button>
    </div>
  );
}
