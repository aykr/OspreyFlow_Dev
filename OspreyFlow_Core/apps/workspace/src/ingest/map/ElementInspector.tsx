// The per-element settings panel — `spec/09_INGEST_STUDIO.md` §4: POLE-first
// type narrowing, match/on-match, per-property bindings, conditions, and a
// per-element handling/provenance override with a live preview.
import { useState } from "react";

import type {
  FieldBinding,
  MapHandlingPreviewResult,
  OntologySchema,
  RecipeCondition,
  RecipeEdge,
  RecipeEntity,
  TransformDescriptor,
} from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Checkbox } from "../../design/primitives/Checkbox";
import { Input } from "../../design/primitives/Input";
import { Panel } from "../../design/primitives/Panel";
import { RadioGroup } from "../../design/primitives/RadioGroup";
import { Select } from "../../design/primitives/Select";
import type { HandlingScheme } from "../api";
import {
  HANDLING_BINDABLE,
  HANDLING_PART_LABELS,
  codeWouldLoosen,
  handlingPartState,
  type HandlingPart,
} from "../handlingParts";
import { FieldBindingEditor } from "./FieldBindingEditor";
import { classificationWouldLoosen, entityTypesForPole, edgeTypesForEndpoints } from "./rowTemplate";

const POLE_CLASSES = ["person", "object", "location", "event", "organisation"] as const;

export type ElementSelection =
  | { kind: "entity"; entity: RecipeEntity }
  | { kind: "edge"; edge: RecipeEdge; fromType: string; toType: string };

export interface ElementInspectorProps {
  selection: ElementSelection;
  ontology: OntologySchema;
  transforms: TransformDescriptor[];
  sourceFieldNames: string[];
  baselineClassification: string;
  classificationOrder: string[];
  /** The scheme's handling, action and sanitisation codes, for a part's literal value. */
  handlingScheme?: HandlingScheme | null;
  /** The source's own marking (the draft's handling), which a literal override may only tighten. */
  sourceHandling?: Record<string, unknown>;
  /** ADR-127 decision 3: the column Connect declared for each handling part (the draft's
   * `handling_columns`). A part can be read from a column only if it is named here. */
  declaredColumns?: Record<string, string>;
  onChangeEntity: (next: RecipeEntity) => void;
  onChangeEdge: (next: RecipeEdge) => void;
  onDelete: () => void;
  onPreviewHandling: (
    handlingOverride: Record<string, unknown> | null,
    provenanceOverride: Record<string, unknown> | null,
  ) => Promise<MapHandlingPreviewResult>;
}

function ConditionEditor({
  condition,
  sourceFieldNames,
  onChange,
}: {
  condition: RecipeCondition | null;
  sourceFieldNames: string[];
  onChange: (next: RecipeCondition | null) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4, 4px)" }}>
      <label style={{ display: "flex", alignItems: "center", gap: "var(--sp-4, 4px)" }}>
        <Checkbox
          checked={condition !== null}
          onChange={(e) =>
            onChange(e.target.checked ? { field: sourceFieldNames[0] ?? "", is: "not_null" } : null)
          }
        />
        Conditional element
      </label>
      {condition && (
        <div style={{ display: "flex", gap: "var(--sp-4, 4px)", alignItems: "center" }}>
          <Select
            value={condition.field}
            onChange={(e) => onChange({ ...condition, field: e.target.value })}
          >
            {sourceFieldNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </Select>
          <Select
            value={condition.equals !== undefined && condition.equals !== null ? "equals" : (condition.is ?? "not_null")}
            onChange={(e) => {
              const v = e.target.value;
              if (v === "equals") onChange({ field: condition.field, equals: "" });
              else onChange({ field: condition.field, is: v as "not_null" | "null" });
            }}
          >
            <option value="not_null">is not null</option>
            <option value="null">is null</option>
            <option value="equals">equals</option>
          </Select>
          {condition.equals !== undefined && condition.equals !== null && (
            <Input
              value={String(condition.equals)}
              onChange={(e) => onChange({ field: condition.field, equals: e.target.value })}
            />
          )}
        </div>
      )}
    </div>
  );
}

/** The values a part may take as a literal: the scheme's own list. A unit has none (a fixed unit
 * need not be one the source declares), so a unit part offers only the default and its column. */
function literalValuesFor(
  part: HandlingPart,
  classificationOrder: string[],
  scheme: HandlingScheme | null | undefined,
): string[] {
  if (part === "classification") return classificationOrder;
  if (part === "handling_code") return Object.keys(scheme?.handling_codes ?? {});
  if (part === "action_code") return Object.keys(scheme?.action_codes ?? {});
  if (part === "sanitisation_code") return Object.keys(scheme?.sanitisation_codes ?? {});
  return [];
}

const FROM_COLUMN = "__column__";
// A binding to a column other than the declared one is shown as itself, so the select never says
// one column while the recipe holds another; choosing it again changes nothing.
const HELD_COLUMN = "__held_column__";

function HandlingOverrideEditor({
  override,
  baselineClassification,
  classificationOrder,
  handlingScheme,
  sourceHandling,
  declaredColumns,
  onChange,
  onPreviewHandling,
}: {
  override: Record<string, unknown> | null;
  baselineClassification: string;
  classificationOrder: string[];
  handlingScheme?: HandlingScheme | null;
  sourceHandling?: Record<string, unknown>;
  declaredColumns: Record<string, string>;
  onChange: (next: Record<string, unknown> | null) => void;
  onPreviewHandling: (
    handlingOverride: Record<string, unknown> | null,
  ) => Promise<MapHandlingPreviewResult>;
}) {
  const [preview, setPreview] = useState<MapHandlingPreviewResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  // A part is a literal, or a `{field: <column>}` binding: never assume a string.
  // A literal looser than the source's own marking is refused at save. Classification is ranked by
  // the scheme's order, the three codes by `merge_handling`'s; a part whose order cannot be
  // computed (no source code, or one the scheme lacks) is not warned about.
  const loosened = HANDLING_BINDABLE.filter((part) => {
    const state = handlingPartState(override, part);
    if (state.kind !== "literal") return false;
    if (part === "classification") {
      return classificationWouldLoosen(classificationOrder, baselineClassification, state.value);
    }
    return codeWouldLoosen(part, handlingScheme, sourceHandling?.[part], state.value);
  });
  // Every declared part must be bound, to the declared column, on every element (Amendment 2): the
  // server refuses the save otherwise, so the editor says which before the analyst gets there.
  const unbound = HANDLING_BINDABLE.filter((part) => {
    const declared = declaredColumns[part];
    if (!declared) return false;
    const state = handlingPartState(override, part);
    return !(state.kind === "column" && state.field === declared);
  });

  async function runPreview() {
    setPreviewError(null);
    try {
      setPreview(await onPreviewHandling(override));
    } catch (err) {
      setPreview(null);
      setPreviewError(err instanceof Error ? err.message : String(err));
    }
  }

  function setPart(part: HandlingPart, choice: string) {
    const next = { ...override };
    if (choice === "") delete next[part];
    else if (choice === HELD_COLUMN) return;
    else if (choice === FROM_COLUMN) next[part] = { field: declaredColumns[part] };
    else next[part] = choice;
    onChange(next);
  }

  // The preview gives the source's default for a bound part, not any row's value, so a bound part
  // is named by its column rather than shown a value it will not have.
  function previewLine(result: MapHandlingPreviewResult): string {
    const shown = HANDLING_BINDABLE.filter(
      (part) => part === "classification" || part === "handling_code" || handlingPartState(override, part).kind === "column",
    );
    const parts = shown.map((part) => {
      const state = handlingPartState(override, part);
      return state.kind === "column"
        ? `${part}: from column ${state.field}`
        : `${part}: ${String(result.handling[part] ?? "")}`;
    });
    return `${parts.join(" · ")} · provenance: ${result.provenance.state}`;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4, 4px)" }}>
      <label style={{ display: "flex", alignItems: "center", gap: "var(--sp-4, 4px)" }}>
        <Checkbox
          checked={override !== null}
          onChange={(e) => onChange(e.target.checked ? {} : null)}
        />
        Override handling for this element
      </label>
      {unbound.map((part) => (
        <div key={part} role="status" style={{ color: "var(--warning)" }}>
          This element does not bind {HANDLING_PART_LABELS[part]}, which the source declares in
          column {declaredColumns[part]}. Saving will be refused.
        </div>
      ))}
      {override !== null && (
        <>
          {HANDLING_BINDABLE.map((part) => {
            const label = HANDLING_PART_LABELS[part];
            const state = handlingPartState(override, part);
            const declared = declaredColumns[part];
            const literals = literalValuesFor(part, classificationOrder, handlingScheme);
            // A literal the recipe already holds stays shown, scheme list or not, so it is neither
            // dropped nor shown as something else.
            const held = state.kind === "literal" && !literals.includes(state.value) ? [state.value] : [];
            return (
              <Select
                key={part}
                aria-label={`${label} for this element`}
                value={
                  state.kind === "column"
                    ? state.field === declared
                      ? FROM_COLUMN
                      : HELD_COLUMN
                    : state.kind === "literal"
                      ? state.value
                      : ""
                }
                onChange={(e) => setPart(part, e.target.value)}
              >
                <option value="">
                  {part === "classification"
                    ? `${label}: use source default (${baselineClassification})`
                    : `${label}: source default`}
                </option>
                {[...held, ...literals].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
                {state.kind === "column" && state.field !== declared && (
                  <option value={HELD_COLUMN}>From column {state.field} (not declared)</option>
                )}
                <option value={FROM_COLUMN} disabled={!declared}>
                  {declared
                    ? `From column ${declared}`
                    : "From column (Connect must declare it first)"}
                </option>
              </Select>
            );
          })}
          {loosened.map((part) => (
            <div key={part} role="alert" style={{ color: "var(--warning)" }}>
              This loosens the source's own {HANDLING_PART_LABELS[part].toLowerCase()},{" "}
              {part === "classification" ? baselineClassification : String(sourceHandling?.[part])} — an
              override may only tighten it. Saving will be rejected.
            </div>
          ))}
          <Button onClick={runPreview}>Preview handling</Button>
          {previewError && <div role="alert">{previewError}</div>}
          {preview && (
            <div style={{ fontFamily: "var(--mono)", fontSize: "0.85em" }}>{previewLine(preview)}</div>
          )}
        </>
      )}
    </div>
  );
}

export function ElementInspector({
  selection,
  ontology,
  transforms,
  sourceFieldNames,
  baselineClassification,
  classificationOrder,
  handlingScheme,
  sourceHandling,
  declaredColumns = {},
  onChangeEntity,
  onChangeEdge,
  onDelete,
  onPreviewHandling,
}: ElementInspectorProps) {
  if (selection.kind === "entity") {
    const { entity } = selection;
    const concreteTypes = entityTypesForPole(ontology, entity.pole_class);
    const properties = entity.properties ?? {};

    function setProperty(name: string, binding: FieldBinding | null) {
      const next = { ...properties };
      if (binding === null) delete next[name];
      else next[name] = binding;
      onChangeEntity({ ...entity, properties: next });
    }

    const typeDef = ontology.entity_types.find((t) => t.name === entity.type);
    // A type's identifiers, then its properties, each once: a Device's IMEI is declared only as an
    // identifier, and Map once offered a Device nothing to set (9 October 2026).
    const availablePropertyNames = [
      ...new Set([...(typeDef?.identifiers ?? []), ...(typeDef?.properties ?? []).map((p) => p.name)]),
    ];

    return (
      <Panel title={`${entity.ref} · ${entity.type}`}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-16, 16px)" }}>
          <div>
            <label>Ref</label>
            <Input
              value={entity.ref}
              onChange={(e) => onChangeEntity({ ...entity, ref: e.target.value })}
            />
          </div>

          <div>
            <label>POLE class</label>
            <Select
              value={entity.pole_class}
              onChange={(e) => {
                const pole = e.target.value;
                const firstType = entityTypesForPole(ontology, pole)[0]?.name ?? "";
                onChangeEntity({ ...entity, pole_class: pole, type: firstType, match_on: null });
              }}
            >
              {POLE_CLASSES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <label>Type</label>
            <Select value={entity.type} onChange={(e) => onChangeEntity({ ...entity, type: e.target.value })}>
              {concreteTypes.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <label>Match on</label>
            <Input
              value={entity.match_on ?? ""}
              placeholder="e.g. value_normalised"
              onChange={(e) => onChangeEntity({ ...entity, match_on: e.target.value || null })}
            />
            <RadioGroup
              name={`on-match-${entity.ref}`}
              aria-label="On match"
              value={entity.on_match ?? "create"}
              onChange={(v) => onChangeEntity({ ...entity, on_match: v as "reference" | "create" })}
              options={[
                { value: "reference", label: "reference existing" },
                { value: "create", label: "create new" },
              ]}
            />
          </div>

          <Panel title="Properties">
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8, 8px)" }}>
              {Object.entries(properties).map(([name, binding]) => (
                <div key={name} style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "var(--sp-8)" }}>
                  <strong>{name}</strong>
                  <FieldBindingEditor
                    binding={binding}
                    sourceFieldNames={sourceFieldNames}
                    transforms={transforms}
                    onChange={(next) => setProperty(name, next)}
                    onRemove={() => setProperty(name, null)}
                  />
                </div>
              ))}
              <Select
                value=""
                onChange={(e) => {
                  if (e.target.value) setProperty(e.target.value, { field: sourceFieldNames[0] });
                }}
              >
                <option value="">+ property</option>
                {availablePropertyNames
                  .filter((n) => !(n in properties))
                  .map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
              </Select>
            </div>
          </Panel>

          <ConditionEditor
            condition={entity.when ?? null}
            sourceFieldNames={sourceFieldNames}
            onChange={(when) => onChangeEntity({ ...entity, when })}
          />

          <HandlingOverrideEditor
            override={entity.handling ?? null}
            baselineClassification={baselineClassification}
            classificationOrder={classificationOrder}
            handlingScheme={handlingScheme}
            sourceHandling={sourceHandling}
            declaredColumns={declaredColumns}
            onChange={(handling) => onChangeEntity({ ...entity, handling })}
            onPreviewHandling={(handlingOverride) =>
              onPreviewHandling(handlingOverride, entity.provenance ?? null)
            }
          />

          {/* ADR-094: content this entity holds (a phone's saved note, photo or video), kept in the
              media store and linked to it by HOLDS. ADR-127: a Document holds only its own text,
              written onto the Document itself, so it is offered that and nothing else (an image or
              a video on a Document is refused at save). */}
          {(() => {
            const isDocument = entity.type === "Document";
            const kindLabel = isDocument ? "Its own text" : "Content this holds";
            const fieldLabel = isDocument ? "Column holding its text" : "Column holding it";
            return (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4, 4px)" }}>
                <label htmlFor="entity-content-kind">{kindLabel}</label>
                <Select
                  id="entity-content-kind"
                  value={entity.content?.kind ?? ""}
                  onChange={(e) => {
                    const kind = e.target.value;
                    const offered =
                      kind === "document_text" ||
                      (!isDocument && (kind === "image_file" || kind === "video_file"));
                    onChangeEntity({
                      ...entity,
                      content: offered
                        ? { kind, field: entity.content?.field ?? sourceFieldNames[0] ?? "" }
                        : null,
                    } as RecipeEntity);
                  }}
                >
                  <option value="">None</option>
                  <option value="document_text">Document text</option>
                  {!isDocument && <option value="image_file">Image file</option>}
                  {!isDocument && <option value="video_file">Video file</option>}
                </Select>
                {!isDocument && (
                  <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
                    An image or a video is named by a path relative to the export's own folder.
                  </span>
                )}
                {entity.content && (
                  <>
                    <label htmlFor="entity-content-field">{fieldLabel}</label>
                    <Select
                      id="entity-content-field"
                      value={entity.content.field}
                      onChange={(e) =>
                        onChangeEntity({
                          ...entity,
                          content: { kind: entity.content!.kind, field: e.target.value },
                        })
                      }
                    >
                      {sourceFieldNames.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </Select>
                  </>
                )}
              </div>
            );
          })()}
          <Button onClick={onDelete}>Delete element</Button>
        </div>
      </Panel>
    );
  }

  const { edge, fromType, toType } = selection;
  const validTypes = edgeTypesForEndpoints(ontology, fromType, toType);
  const properties = edge.properties ?? {};

  function setEdgeProperty(name: string, binding: FieldBinding | null) {
    const next = { ...properties };
    if (binding === null) delete next[name];
    else next[name] = binding;
    onChangeEdge({ ...edge, properties: next });
  }

  const edgeTypeDef = ontology.edge_types.find((t) => t.name === edge.type);
  const availableEdgePropertyNames = (edgeTypeDef?.properties ?? []).map((p) => p.name);

  return (
    <Panel title={`${edge.from} → ${edge.to} · ${edge.type}`}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-16, 16px)" }}>
        <div>
          <label>Type</label>
          <Select value={edge.type} onChange={(e) => onChangeEdge({ ...edge, type: e.target.value })}>
            {validTypes.map((t) => (
              <option key={t.name} value={t.name}>
                {t.name}
              </option>
            ))}
          </Select>
        </div>

        {edgeTypeDef?.temporal && (
          // A link type that can carry a time need not: a link with none records no event. The
          // editor shows what the recipe holds — it once showed a binding to the first column that
          // was never saved (found building the AML deck, 11 October 2026).
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4, 4px)" }}>
            <label htmlFor="edge-temporal-mode">When it occurred</label>
            <Select
              id="edge-temporal-mode"
              value={edge.temporal ? "column" : ""}
              onChange={(e) =>
                onChangeEdge(
                  e.target.value === "column"
                    ? { ...edge, temporal: { at: { field: sourceFieldNames[0] ?? "" } } }
                    : { ...edge, temporal: null, content: null },
                )
              }
            >
              <option value="">Not recorded</option>
              <option value="column">From a column</option>
            </Select>
            {edge.temporal && (
              <FieldBindingEditor
                binding={edge.temporal.at}
                sourceFieldNames={sourceFieldNames}
                transforms={transforms}
                onChange={(at) => onChangeEdge({ ...edge, temporal: { ...edge.temporal, at } })}
              />
            )}
          </div>
        )}

        {edgeTypeDef?.temporal && edge.temporal && (
          // ADR-127 decision 11: a link can be a span. Its end is one column of the source; an
          // empty cell in it is a span still running. With none recorded the link is one moment.
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4, 4px)" }}>
            <label htmlFor="edge-temporal-end-mode">When it ended</label>
            <Select
              id="edge-temporal-end-mode"
              value={edge.temporal.valid_to ? "column" : ""}
              onChange={(e) => {
                const start = { ...edge.temporal! };
                delete start.valid_to;
                onChangeEdge({
                  ...edge,
                  temporal:
                    e.target.value === "column"
                      ? {
                          ...start,
                          valid_to: {
                            field: sourceFieldNames[0] ?? "",
                            ...(transforms.some((t) => t.name === "datetime")
                              ? { transform: "datetime" }
                              : {}),
                          },
                        }
                      : start,
                });
              }}
            >
              <option value="">Not recorded (one moment)</option>
              <option value="column">From a column</option>
            </Select>
            {edge.temporal.valid_to && (
              <>
                <Select
                  aria-label="Column holding when it ended"
                  value={edge.temporal.valid_to.field ?? ""}
                  onChange={(e) =>
                    onChangeEdge({
                      ...edge,
                      temporal: { ...edge.temporal!, valid_to: { ...edge.temporal!.valid_to!, field: e.target.value } },
                    })
                  }
                >
                  {sourceFieldNames.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </Select>
                <Select
                  aria-label="Transform for when it ended"
                  value={edge.temporal.valid_to.transform ?? ""}
                  onChange={(e) => {
                    const rest = { ...edge.temporal!.valid_to! };
                    delete rest.transform;
                    onChangeEdge({
                      ...edge,
                      temporal: {
                        ...edge.temporal!,
                        valid_to: e.target.value ? { ...rest, transform: e.target.value } : rest,
                      },
                    });
                  }}
                >
                  <option value="">No transform</option>
                  {transforms
                    .filter((t) => t.arity <= 1 && (t.parts ?? []).length === 0)
                    .map((t) => (
                      <option key={t.name} value={t.name}>
                        {t.name}
                      </option>
                    ))}
                </Select>
                <span style={{ color: "var(--text-tertiary)" }}>
                  An empty cell means it is still going.
                </span>
              </>
            )}
          </div>
        )}

        {edgeTypeDef?.temporal && edge.temporal && (
          // ADR-094: the column holding this link's message or document text, kept on its events
          // where the reader and extraction read it. Only a link with a time has events.
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4, 4px)" }}>
            <label htmlFor="edge-content-kind">Text the model can read</label>
            <Select
              id="edge-content-kind"
              value={edge.content?.kind ?? ""}
              onChange={(e) => {
                const kind = e.target.value;
                onChangeEdge({
                  ...edge,
                  content:
                    kind === "message_text" || kind === "document_text"
                      ? { kind, field: edge.content?.field ?? sourceFieldNames[0] ?? "" }
                      : null,
                });
              }}
            >
              <option value="">None</option>
              <option value="message_text">Message text</option>
              <option value="document_text">Document text</option>
            </Select>
            {edge.content && (
              <>
                <label htmlFor="edge-content-field">Column holding the text</label>
                <Select
                  id="edge-content-field"
                  value={edge.content.field}
                  onChange={(e) =>
                    onChangeEdge({ ...edge, content: { kind: edge.content!.kind, field: e.target.value } })
                  }
                >
                  {sourceFieldNames.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </Select>
              </>
            )}
          </div>
        )}

        <Panel title="Properties">
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8, 8px)" }}>
            {Object.entries(properties).map(([name, binding]) => (
              <div key={name} style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "var(--sp-8)" }}>
                <strong>{name}</strong>
                <FieldBindingEditor
                  binding={binding}
                  sourceFieldNames={sourceFieldNames}
                  transforms={transforms}
                  onChange={(next) => setEdgeProperty(name, next)}
                  onRemove={() => setEdgeProperty(name, null)}
                />
              </div>
            ))}
            <Select
              value=""
              onChange={(e) => {
                if (e.target.value) setEdgeProperty(e.target.value, { field: sourceFieldNames[0] });
              }}
            >
              <option value="">+ property</option>
              {availableEdgePropertyNames
                .filter((n) => !(n in properties))
                .map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
            </Select>
          </div>
        </Panel>

        <ConditionEditor
          condition={edge.when ?? null}
          sourceFieldNames={sourceFieldNames}
          onChange={(when) => onChangeEdge({ ...edge, when })}
        />

        <HandlingOverrideEditor
          override={edge.handling ?? null}
          baselineClassification={baselineClassification}
          classificationOrder={classificationOrder}
          handlingScheme={handlingScheme}
          sourceHandling={sourceHandling}
          declaredColumns={declaredColumns}
          onChange={(handling) => onChangeEdge({ ...edge, handling })}
          onPreviewHandling={(handlingOverride) => onPreviewHandling(handlingOverride, edge.provenance ?? null)}
        />

        <Button onClick={onDelete}>Delete element</Button>
      </div>
    </Panel>
  );
}
