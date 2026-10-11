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

function HandlingOverrideEditor({
  override,
  baselineClassification,
  classificationOrder,
  onChange,
  onPreviewHandling,
}: {
  override: Record<string, unknown> | null;
  baselineClassification: string;
  classificationOrder: string[];
  onChange: (next: Record<string, unknown> | null) => void;
  onPreviewHandling: (
    handlingOverride: Record<string, unknown> | null,
  ) => Promise<MapHandlingPreviewResult>;
}) {
  const [preview, setPreview] = useState<MapHandlingPreviewResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const classification = (override?.classification as string | undefined) ?? "";
  const wouldLoosen = classificationWouldLoosen(classificationOrder, baselineClassification, classification || null);

  async function runPreview() {
    setPreviewError(null);
    try {
      setPreview(await onPreviewHandling(override));
    } catch (err) {
      setPreview(null);
      setPreviewError(err instanceof Error ? err.message : String(err));
    }
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
      {override !== null && (
        <>
          <Select
            value={classification}
            onChange={(e) => onChange({ ...override, classification: e.target.value || undefined })}
          >
            <option value="">(use source default: {baselineClassification})</option>
            {classificationOrder.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
          {wouldLoosen && (
            <div role="alert" style={{ color: "var(--warning)" }}>
              This loosens the source's own {baselineClassification} marking — an override may
              only tighten it. Saving will be rejected.
            </div>
          )}
          <Button onClick={runPreview}>Preview handling</Button>
          {previewError && <div role="alert">{previewError}</div>}
          {preview && (
            <div style={{ fontFamily: "var(--mono)", fontSize: "0.85em" }}>
              classification: {preview.handling.classification} · handling_code:{" "}
              {preview.handling.handling_code} · provenance: {preview.provenance.state}
            </div>
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
            onChange={(handling) => onChangeEntity({ ...entity, handling })}
            onPreviewHandling={(handlingOverride) =>
              onPreviewHandling(handlingOverride, entity.provenance ?? null)
            }
          />

          {/* ADR-094: content this entity holds (a phone's saved note, photo or video), kept in the
              media store and linked to it by HOLDS. */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4, 4px)" }}>
            <label htmlFor="entity-content-kind">Content this holds</label>
            <Select
              id="entity-content-kind"
              value={entity.content?.kind ?? ""}
              onChange={(e) => {
                const kind = e.target.value;
                onChangeEntity({
                  ...entity,
                  content:
                    kind === "document_text" || kind === "image_file" || kind === "video_file"
                      ? { kind, field: entity.content?.field ?? sourceFieldNames[0] ?? "" }
                      : null,
                });
              }}
            >
              <option value="">None</option>
              <option value="document_text">Document text</option>
              <option value="image_file">Image file</option>
              <option value="video_file">Video file</option>
            </Select>
            <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
              An image or a video is named by a path relative to the export's own folder.
            </span>
            {entity.content && (
              <>
                <label htmlFor="entity-content-field">Column holding it</label>
                <Select
                  id="entity-content-field"
                  value={entity.content.field}
                  onChange={(e) =>
                    onChangeEntity({ ...entity, content: { kind: entity.content!.kind, field: e.target.value } })
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
                onChange={(at) => onChangeEdge({ ...edge, temporal: { at } })}
              />
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
          onChange={(handling) => onChangeEdge({ ...edge, handling })}
          onPreviewHandling={(handlingOverride) => onPreviewHandling(handlingOverride, edge.provenance ?? null)}
        />

        <Button onClick={onDelete}>Delete element</Button>
      </div>
    </Panel>
  );
}
