// The left panel — `spec/09_INGEST_STUDIO.md` §4: profiled source fields,
// the row scrubber ("the template is always shown bound to a real row, and
// the analyst can page through"), and the unmapped-fields list ("Unmapped
// fields are shown, always").
import type { ColumnProfile, MapSampleRow } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { Panel } from "../../design/primitives/Panel";

export interface SourceFieldsPanelProps {
  columns: ColumnProfile[];
  sampleRow: MapSampleRow | null;
  boundFieldNames: Set<string>;
  unmappedFieldNames: string[];
  ignoredNotes: Map<string, string | null>;
  onRowChange: (delta: 1 | -1) => void;
  onIgnoreField: (field: string, note: string | null) => void;
  onUnignoreField: (field: string) => void;
}

export function SourceFieldsPanel({
  columns,
  sampleRow,
  boundFieldNames,
  unmappedFieldNames,
  ignoredNotes,
  onRowChange,
  onIgnoreField,
  onUnignoreField,
}: SourceFieldsPanelProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-16, 16px)", height: "100%", overflow: "auto" }}>
      <Panel title="Source fields">
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8, 8px)" }}>
          {columns.map((column) => {
            const bound = boundFieldNames.has(column.name);
            const ignored = ignoredNotes.has(column.name);
            return (
              <div
                key={column.name}
                draggable
                onDragStart={(e) => e.dataTransfer.setData("text/x-osprey-field", column.name)}
                style={{
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--r-panel)",
                  padding: "var(--sp-8)",
                  opacity: bound || ignored ? 0.6 : 1,
                  cursor: "grab",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <strong>{column.name}</strong>
                  <span style={{ color: "var(--text-tertiary)" }}>
                    {column.inferred_type} ({Math.round(column.type_confidence * 100)}%)
                  </span>
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: "0.85em", color: "var(--text-secondary)" }}>
                  {sampleRow?.values[column.name] ?? column.sample_values?.[0] ?? ""}
                </div>
                {(column.pattern_matches ?? []).map((m) => (
                  <span
                    key={m.adapter}
                    style={{
                      display: "inline-block",
                      marginTop: "var(--sp-4)",
                      border: "1px solid var(--border-strong)",
                      borderRadius: "var(--r-panel)",
                      padding: "0 var(--sp-8)",
                      fontSize: "0.8em",
                    }}
                  >
                    {m.adapter} {Math.round(m.match_rate * 100)}%
                  </span>
                ))}
              </div>
            );
          })}
        </div>
      </Panel>

      {sampleRow && (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-8, 8px)" }}>
          <Button onClick={() => onRowChange(-1)} disabled={sampleRow.row_index === 0} aria-label="Previous row">
            ◂
          </Button>
          <span>Row {sampleRow.row_index + 1} of sample</span>
          <Button onClick={() => onRowChange(1)} disabled={sampleRow.is_last_row} aria-label="Next row">
            ▸
          </Button>
        </div>
      )}
      {sampleRow?.values_masked && (
        <div role="status" style={{ color: "var(--text-secondary)" }}>
          You aren't cleared for this source's handling marking, so the scrubbed row is shown
          shape-masked.
        </div>
      )}

      {unmappedFieldNames.length > 0 && (
        <Panel title={`⚠ ${unmappedFieldNames.length} field(s) unmapped`}>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8, 8px)" }}>
            {unmappedFieldNames.map((name) => (
              <UnmappedFieldRow key={name} field={name} onIgnore={onIgnoreField} />
            ))}
          </div>
        </Panel>
      )}

      {ignoredNotes.size > 0 && (
        <Panel title="Ignored fields">
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8, 8px)" }}>
            {[...ignoredNotes.entries()].map(([field, note]) => (
              <div key={field} style={{ display: "flex", justifyContent: "space-between", gap: "var(--sp-8)" }}>
                <span>
                  <strong>{field}</strong>
                  {note && <> — {note}</>}
                </span>
                <Button onClick={() => onUnignoreField(field)}>Unignore</Button>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

function UnmappedFieldRow({
  field,
  onIgnore,
}: {
  field: string;
  onIgnore: (field: string, note: string | null) => void;
}) {
  return (
    <div style={{ display: "flex", gap: "var(--sp-8, 8px)", alignItems: "center" }}>
      <strong style={{ flex: 1 }}>{field}</strong>
      <Input
        placeholder="note (optional)"
        onKeyDown={(e) => {
          if (e.key === "Enter") onIgnore(field, (e.target as HTMLInputElement).value || null);
        }}
      />
      <Button onClick={() => onIgnore(field, null)}>Ignore</Button>
    </div>
  );
}
