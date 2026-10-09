// Stage 3 of the Ingest Studio — `spec/09_INGEST_STUDIO.md` §4. Fetches the
// draft, its profile (for the source-fields panel — Map is unreachable
// until Profile has succeeded, same gate `ProfileScreen.tsx` enforces),
// the ontology schema (POLE-first type narrowing) and the transform
// catalogue; owns the in-progress `RowTemplate`/`unmapped_fields` draft
// state locally until "Save draft" persists it.
//
// **Disclosed simplification.** §4's keyboard path ("select both and press
// Enter") is not wired end-to-end here — binding a field is drag-and-drop
// only (a source field chip onto a property's binding editor). Every other
// action in this screen (adding an element, changing a type, editing a
// binding, saving) is a plain focusable control reachable by Tab, so
// nothing is keyboard-*inaccessible*; only this one specific shortcut path
// is deferred, the same way `GlassCanvas.tsx` discloses its own curved-edge
// gap rather than silently shipping a partial version of the spec.
import { useEffect, useState } from "react";

import type {
  ColumnProfile,
  MapSampleRow,
  OntologySchema,
  RecipeEdge,
  RecipeEntity,
  RowTemplate,
  StudioRecipeDraft,
  TransformDescriptor,
  UnmappedField,
} from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import {
  ProfileError,
  RowTemplateSaveError,
  fetchDraft,
  fetchHandlingScheme,
  fetchOntologySchema,
  fetchProfile,
  fetchSampleRow,
  fetchTransforms,
  previewHandling,
  updateRowTemplate,
  type HandlingScheme,
} from "../api";
import { ElementInspector, type ElementSelection } from "./ElementInspector";
import { MapCanvas, type MapSelection } from "./MapCanvas";
import { SourceFieldsPanel } from "./SourceFieldsPanel";
import { edgeTypesForEndpoints, entityTypesForPole, findEdge, findEntity, nextEntityRef, unmappedFieldNames, updateEntityByRef, boundFieldNames as boundFieldNamesOf } from "./rowTemplate";

export interface MapScreenProps {
  apiBaseUrl: string;
  /** ADR-099 Amendment 3: the case whose dataset the recipe belongs to. */
  investigationId: string;
  bearerToken: string;
  recipeId: string;
  onBack: () => void;
  /** Fired whenever this screen's own idea of the draft changes — a fresh
   * fetch or a successful "Save draft" — so `IngestStudio.tsx` can gate
   * Verify on `row_template` being present without reaching into this
   * screen's internal state (`ConnectScreen.tsx`'s own `onDraftChange`
   * follows the same shape). */
  onDraftChange?: (draft: StudioRecipeDraft) => void;
}

const ERROR_MESSAGES: Record<string, string> = {
  recipe_not_ready_for_profile:
    "This source isn't ready for Map yet — go back to Connect and answer the location, handling marking and legal basis.",
  connector_not_available: "This source's connector has no reader yet, so it can't be mapped.",
  source_unreadable: "The source couldn't be read — check it's still at the location Connect recorded.",
  source_handling_incomplete: "This source's handling marking is incomplete — go back to Connect.",
  handling_loosened:
    "An element's handling override is less restrictive than the source's own marking — an override may only tighten it, never loosen it.",
  forbidden: "You don't hold the source_author role needed to save a mapping.",
};

function friendlyError(err: unknown): string {
  if (err instanceof ProfileError || err instanceof RowTemplateSaveError) {
    return ERROR_MESSAGES[err.code] ?? err.message;
  }
  return err instanceof Error ? err.message : String(err);
}

const EMPTY_TEMPLATE: RowTemplate = { entities: [], edges: [] };

export function MapScreen({
  apiBaseUrl,
  investigationId,
  bearerToken,
  recipeId,
  onBack,
  onDraftChange,
}: MapScreenProps) {
  const [draft, setDraft] = useState<StudioRecipeDraft | null>(null);
  const [columns, setColumns] = useState<ColumnProfile[] | null>(null);
  const [ontology, setOntology] = useState<OntologySchema | null>(null);
  const [transforms, setTransforms] = useState<TransformDescriptor[]>([]);
  const [scheme, setScheme] = useState<HandlingScheme | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [template, setTemplate] = useState<RowTemplate>(EMPTY_TEMPLATE);
  const [ignored, setIgnored] = useState<Map<string, string | null>>(new Map());
  const [selection, setSelection] = useState<MapSelection>(null);
  const [linking, setLinking] = useState(false);
  const [linkFromRef, setLinkFromRef] = useState<string | null>(null);

  const [rowIndex, setRowIndex] = useState(0);
  const [sampleRow, setSampleRow] = useState<MapSampleRow | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      fetchDraft(apiBaseUrl, bearerToken, investigationId, recipeId),
      fetchProfile(apiBaseUrl, bearerToken, investigationId, recipeId),
      fetchOntologySchema(apiBaseUrl, bearerToken),
      fetchTransforms(apiBaseUrl, bearerToken),
      fetchHandlingScheme(apiBaseUrl, bearerToken),
    ])
      .then(([draftResult, profileResult, ontologyResult, transformsResult, schemeResult]) => {
        if (cancelled) return;
        setDraft(draftResult);
        onDraftChange?.(draftResult);
        setColumns(profileResult.columns);
        setOntology(ontologyResult);
        setTransforms(transformsResult);
        setScheme(schemeResult);
        setTemplate(draftResult.row_template ?? EMPTY_TEMPLATE);
        setIgnored(new Map((draftResult.unmapped_fields ?? []).map((f) => [f.field, f.note ?? null])));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(friendlyError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, recipeId, onDraftChange, investigationId]);

  useEffect(() => {
    if (loading || error) return;
    let cancelled = false;
    fetchSampleRow(apiBaseUrl, bearerToken, investigationId, recipeId, rowIndex)
      .then((row) => {
        if (!cancelled) setSampleRow(row);
      })
      .catch(() => {
        // Non-fatal: the source-fields panel falls back to Profile's own
        // cached samples when no scrubbed row is available.
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, recipeId, rowIndex, loading, error, investigationId]);

  if (loading) return <p style={{ padding: "var(--sp-16)", color: "var(--text-secondary)" }}>Loading…</p>;
  if (error || !draft || !columns || !ontology) {
    return (
      <div style={{ padding: "var(--sp-16)" }}>
        <Button onClick={onBack}>← Connect</Button>
        <div role="alert" style={{ marginTop: "var(--sp-8)" }}>
          {error ?? "Map could not load this source."}
        </div>
      </div>
    );
  }

  // One rule for which columns are mapped, shared with the unmapped list (it was a second copy).
  const boundFieldNames = boundFieldNamesOf(template);
  const unmapped = unmappedFieldNames(
    columns.map((c) => c.name),
    template,
    new Set(ignored.keys()),
  );
  // A `const` alias so the guard above's narrowing of `ontology` to
  // `OntologySchema` (not `| null`) survives into the nested function
  // declarations below — TypeScript resets narrowing of a captured
  // variable at a function boundary even for a `const`.
  const ontologySchema = ontology;

  function updateEntity(ref: string, next: RecipeEntity) {
    // By the ref it had, not the one it may now be given: a rename was dropped (9 October 2026).
    const renamed = next.ref !== ref && !template.entities.some((e) => e.ref === next.ref);
    setTemplate((t) => updateEntityByRef(t, ref, next));
    if (renamed) setSelection({ kind: "entity", ref: next.ref });
  }

  function updateEdge(index: number, next: RecipeEdge) {
    setTemplate((t) => ({ ...t, edges: (t.edges ?? []).map((e, i) => (i === index ? next : e)) }));
  }

  function deleteSelection() {
    if (selection?.kind === "entity") {
      const ref = selection.ref;
      setTemplate((t) => ({
        entities: t.entities.filter((e) => e.ref !== ref),
        // An entity's own edges go with it — an edge with a dangling
        // endpoint is not a state this screen ever produces.
        edges: (t.edges ?? []).filter((e) => e.from !== ref && e.to !== ref),
      }));
    } else if (selection?.kind === "edge") {
      const index = selection.index;
      setTemplate((t) => ({ ...t, edges: (t.edges ?? []).filter((_, i) => i !== index) }));
    }
    setSelection(null);
  }

  function handleAddEntity() {
    const objectTypes = entityTypesForPole(ontologySchema, "object");
    const ref = nextEntityRef(template.entities);
    const entity: RecipeEntity = {
      ref,
      pole_class: "object",
      type: objectTypes[0]?.name ?? "",
      on_match: "create",
      properties: {},
    };
    setTemplate((t) => ({ ...t, entities: [...t.entities, entity] }));
    setSelection({ kind: "entity", ref });
  }

  function handleCanvasSelect(sel: MapSelection) {
    if (linking && sel?.kind === "entity") {
      if (!linkFromRef) {
        setLinkFromRef(sel.ref);
        return;
      }
      if (sel.ref !== linkFromRef) {
        const fromEntity = findEntity(template, linkFromRef);
        const toEntity = findEntity(template, sel.ref);
        const edgeType =
          fromEntity && toEntity
            ? edgeTypesForEndpoints(ontologySchema, fromEntity.type, toEntity.type)[0]?.name
            : undefined;
        if (edgeType) {
          const edge: RecipeEdge = { type: edgeType, from: linkFromRef, to: sel.ref, properties: {} };
          setTemplate((t) => ({ ...t, edges: [...(t.edges ?? []), edge] }));
          setSelection({ kind: "edge", index: (template.edges ?? []).length });
        } else {
          setSaveError("No ontology edge type connects these two entity types.");
        }
      }
      setLinking(false);
      setLinkFromRef(null);
      return;
    }
    setSelection(sel);
  }

  const inspectorSelection: ElementSelection | null =
    selection?.kind === "entity"
      ? (() => {
          const entity = findEntity(template, selection.ref);
          return entity ? { kind: "entity" as const, entity } : null;
        })()
      : selection?.kind === "edge"
        ? (() => {
            const edge = findEdge(template, selection.index);
            if (!edge) return null;
            const fromEntity = findEntity(template, edge.from);
            const toEntity = findEntity(template, edge.to);
            return fromEntity && toEntity
              ? { kind: "edge" as const, edge, fromType: fromEntity.type, toType: toEntity.type }
              : null;
          })()
        : null;

  const baselineClassification = (draft.handling as { classification?: string }).classification ?? "";

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      const unmappedFields: UnmappedField[] = [...ignored.entries()].map(([field, note]) => ({
        field,
        action: "ignore",
        note: note ?? undefined,
      }));
      const updated = await updateRowTemplate(apiBaseUrl, bearerToken, investigationId, recipeId, template, unmappedFields);
      setDraft(updated);
      onDraftChange?.(updated);
    } catch (err) {
      setSaveError(friendlyError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)", padding: "var(--sp-16)" }}>
        <Button onClick={onBack}>← Connect</Button>
        <h1 style={{ fontSize: "1.1em", margin: 0 }}>Map — {draft.label}</h1>
        <div style={{ flex: 1 }} />
        {saveError && (
          <span role="alert" style={{ color: "var(--warning)" }}>
            {saveError}
          </span>
        )}
        <Button onClick={handleSave} variant="primary" disabled={saving}>
          {saving ? "Saving…" : "Save draft"}
        </Button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "280px 1fr 340px", flex: 1, minHeight: 0, gap: "var(--sp-8)" }}>
        <SourceFieldsPanel
          columns={columns}
          sampleRow={sampleRow}
          boundFieldNames={boundFieldNames}
          unmappedFieldNames={unmapped}
          ignoredNotes={new Map(ignored)}
          onRowChange={(delta) => setRowIndex((i) => Math.max(0, i + delta))}
          onIgnoreField={(field, note) => setIgnored((m) => new Map(m).set(field, note))}
          onUnignoreField={(field) =>
            setIgnored((m) => {
              const next = new Map(m);
              next.delete(field);
              return next;
            })
          }
        />

        <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div style={{ display: "flex", gap: "var(--sp-8)", padding: "var(--sp-8)" }}>
            <Button onClick={handleAddEntity}>+ entity</Button>
            <Button
              onClick={() => {
                setLinking((v) => !v);
                setLinkFromRef(null);
              }}
              variant={linking ? "primary" : "default"}
            >
              {linking ? "click two entities…" : "+ link"}
            </Button>
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            <MapCanvas
              template={template}
              ontology={ontology}
              selection={selection}
              linkFromRef={linkFromRef}
              onSelect={handleCanvasSelect}
              onBackgroundClick={() => setSelection(null)}
            />
          </div>
        </div>

        <div style={{ overflow: "auto" }}>
          {inspectorSelection ? (
            <ElementInspector
              selection={inspectorSelection}
              ontology={ontology}
              transforms={transforms}
              sourceFieldNames={columns.map((c) => c.name)}
              baselineClassification={baselineClassification}
              classificationOrder={scheme?.classification ?? []}
              onChangeEntity={(next) =>
                selection?.kind === "entity" ? updateEntity(selection.ref, next) : undefined
              }
              onChangeEdge={(next) =>
                selection?.kind === "edge" ? updateEdge(selection.index, next) : undefined
              }
              onDelete={deleteSelection}
              onPreviewHandling={(handlingOverride, provenanceOverride) =>
                previewHandling(apiBaseUrl, bearerToken, investigationId, recipeId, {
                  row_index: rowIndex,
                  handling_override: handlingOverride,
                  provenance_override: provenanceOverride,
                })
              }
            />
          ) : (
            <p style={{ padding: "var(--sp-16)", color: "var(--text-secondary)" }}>
              Select an element to edit its settings, or add one with "+ entity".
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
