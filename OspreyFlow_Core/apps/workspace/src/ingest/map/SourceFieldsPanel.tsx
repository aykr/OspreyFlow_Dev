// The left panel — `spec/09_INGEST_STUDIO.md` §4: profiled source fields,
// the row scrubber ("the template is always shown bound to a real row, and
// the analyst can page through"), and the unmapped-fields list ("Unmapped
// fields are shown, always").
import { useState } from "react";

import type { ColumnProfile, MapSampleRow } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { Panel } from "../../design/primitives/Panel";
import { percent } from "../percent";

export interface SourceFieldsPanelProps {
  columns: ColumnProfile[];
  sampleRow: MapSampleRow | null;
  boundFieldNames: Set<string>;
  unmappedFieldNames: string[];
  ignoredNotes: Map<string, string | null>;
  onRowChange: (delta: 1 | -1) => void;
  onIgnoreField: (field: string, note: string | null) => void;
  onUnignoreField: (field: string) => void;
  /** Which registered source the pipeline reads, in words (ADR-140 Amendment 6); the fields are
   * still the pipeline's own profile. `null`: nothing to say (no dataset, or still reading). */
  readsFrom?: string | null;
  /** Spec 09 §4's keyboard bind: the column chosen to bind, and choosing or letting one go. */
  chosenColumn?: string | null;
  onChooseColumn?: (column: string | null) => void;
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
  readsFrom = null,
  chosenColumn = null,
  onChooseColumn,
}: SourceFieldsPanelProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-16, 16px)", height: "100%", overflow: "auto" }}>
      <Panel title="Source fields">
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8, 8px)" }}>
          {readsFrom && (
            <p className="label" role="status" style={{ margin: 0 }}>
              {readsFrom}
            </p>
          )}
          {chosenColumn && (
            <p role="status" style={{ margin: 0 }}>
              {`${chosenColumn} is chosen: press “Bind ${chosenColumn} here” on a binding in the inspector.`}
            </p>
          )}
          {columns.map((column) => {
            const bound = boundFieldNames.has(column.name);
            const ignored = ignoredNotes.has(column.name);
            const isChosen = chosenColumn === column.name;
            return (
              <div
                key={column.name}
                draggable
                onDragStart={(e) => e.dataTransfer.setData("text/x-osprey-field", column.name)}
                style={{
                  // Bound columns are outlined and say so (brief §6.5), never faded: an `opacity` of
                  // 0.6 put every word on a bound column below 4.5:1, found by phase 6's first axe
                  // scan of Map with a column bound (7 November 2026).
                  border: isChosen
                    ? "2px solid var(--border-strong)"
                    : bound
                      ? "1px solid var(--border-strong)"
                      : "1px dashed var(--border-subtle)",
                  borderRadius: "var(--r-panel)",
                  padding: "var(--sp-8)",
                  cursor: "grab",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--sp-8)", alignItems: "center" }}>
                  <strong>{column.name}</strong>
                  <span style={{ color: "var(--text-secondary)" }}>
                    {bound ? "bound · " : ignored ? "ignored · " : ""}
                    {column.inferred_type} ({percent(column.type_confidence)})
                  </span>
                </div>
                {onChooseColumn && (
                  <Button
                    aria-pressed={isChosen}
                    aria-label={isChosen ? `Let go column ${column.name}` : `Choose column ${column.name}`}
                    onClick={() => onChooseColumn(isChosen ? null : column.name)}
                  >
                    {isChosen ? "Let go" : "Choose"}
                  </Button>
                )}
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
                    {m.adapter} {percent(m.match_rate)}
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
  // The note is held here so Ignore keeps it; the button once ignored with no note, and only Enter
  // kept what was typed (9 October 2026).
  const [note, setNote] = useState("");
  const ignore = () => onIgnore(field, note.trim() || null);
  return (
    <div style={{ display: "flex", gap: "var(--sp-8, 8px)", alignItems: "center" }}>
      <strong style={{ flex: 1 }}>{field}</strong>
      {/* Each row's note box and button are named with their column: every row once read only
          "Ignore" and a placeholder, so a keyboard or screen-reader user could not tell which column
          a control ignored (found building phase 6's exit, 8 November 2026). */}
      <Input
        aria-label={`Note for ignoring ${field}`}
        placeholder="note (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") ignore();
        }}
      />
      <Button aria-label={`Ignore ${field}`} onClick={ignore}>
        Ignore
      </Button>
    </div>
  );
}
