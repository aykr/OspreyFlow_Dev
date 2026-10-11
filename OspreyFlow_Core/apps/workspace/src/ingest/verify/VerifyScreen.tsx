// Stage 4 of the Ingest Studio — `spec/09_INGEST_STUDIO.md` §5. A dry run:
// no persistent write happens anywhere, but an `on_match: reference` lookup
// against the *existing* graph is real, going through the ordinary
// `GraphPort.find_node` under this principal's own clearance
// (`services/ingest/engine.py`'s `dry_run_recipe`) — which is what makes
// "an author cannot use a dry run to see material they could not otherwise
// see" mechanically true rather than a convention. Verify is a deliberate
// action (a "Run verify" button), not an auto-run-on-visit, since it does
// real graph reads the analyst should choose when to spend.
//
// The rendered graph reuses `GlassCanvas` — the *ordinary* canvas, not
// `../map/MapCanvas.tsx`'s own lightweight row-template editor — over a
// throwaway `createWorkingSet()` populated the same way a real snapshot
// populates a live one. §5: "rendered in the ordinary canvas... a wrong
// mapping is usually obvious at a glance."
import { useEffect, useState } from "react";

import type {
  EdgeTypeDef,
  StudioRecipeDraft,
  VerifyReport,
} from "../../../../../packages/schemas/generated";
import { GlassCanvas } from "../../canvas/GlassCanvas";
import { Button } from "../../design/primitives/Button";
import { Panel } from "../../design/primitives/Panel";
import { Table, type TableColumn } from "../../design/primitives/Table";
import { OntologyRegistry } from "../../ontology/schema";
import { createWorkingSet, type WorkingSet } from "../../workingset/store";
import { ProfileError, fetchDraft, fetchOntologySchema, runVerify } from "../api";

export interface VerifyScreenProps {
  apiBaseUrl: string;
  /** ADR-099 Amendment 3: the case whose dataset the recipe belongs to. */
  investigationId: string;
  bearerToken: string;
  recipeId: string;
  onBack: () => void;
}

const ERROR_MESSAGES: Record<string, string> = {
  recipe_not_ready_for_profile:
    "This source isn't ready for Verify yet — go back to Connect and answer the location, handling marking and legal basis.",
  row_template_missing:
    "This source has no mapping yet — go to Map and save a row template before verifying.",
  connector_not_available: "This source's connector has no reader yet, so it can't be verified.",
  source_unreadable: "The source couldn't be read — check it's still at the location Connect recorded.",
  source_handling_incomplete: "This source's handling marking is incomplete — go back to Connect.",
  ontology_violation:
    "This recipe doesn't match the active ontology — open it in Map and check the affected element's type and properties.",
};

function friendlyError(err: unknown): string {
  if (err instanceof ProfileError) return ERROR_MESSAGES[err.code] ?? err.message;
  return err instanceof Error ? err.message : String(err);
}

interface EntityCountRow {
  type: string;
  created: number;
  referenced: number;
}

interface EdgeCountRow {
  type: string;
  created: number;
}

export function VerifyScreen({ apiBaseUrl,
  investigationId, bearerToken, recipeId, onBack }: VerifyScreenProps) {
  const [draft, setDraft] = useState<StudioRecipeDraft | null>(null);
  const [registry, setRegistry] = useState<OntologyRegistry | null>(null);
  const [edgeTypes, setEdgeTypes] = useState<EdgeTypeDef[]>([]);
  const [report, setReport] = useState<VerifyReport | null>(null);
  const [workingSet, setWorkingSet] = useState<WorkingSet | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchDraft(apiBaseUrl, bearerToken, investigationId, recipeId).then((d) => {
      if (!cancelled) setDraft(d);
    });
    void fetchOntologySchema(apiBaseUrl, bearerToken).then((schema) => {
      if (cancelled) return;
      setRegistry(new OntologyRegistry(schema));
      setEdgeTypes(schema.edge_types);
    });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, recipeId, investigationId]);

  async function handleRunVerify() {
    setRunning(true);
    setError(null);
    try {
      const result = await runVerify(apiBaseUrl, bearerToken, investigationId, recipeId);
      const ws = createWorkingSet();
      for (const node of result.nodes ?? []) {
        ws.graph.addNode(node.id, { data: node });
      }
      for (const edge of result.edges ?? []) {
        ws.graph.addEdgeWithKey(edge.id, edge.source, edge.target, { data: edge });
      }
      setReport(result);
      setWorkingSet(ws);
    } catch (err) {
      setError(friendlyError(err));
      setReport(null);
      setWorkingSet(null);
    } finally {
      setRunning(false);
    }
  }

  const entityRows: EntityCountRow[] = Object.entries(report?.entities_by_type ?? {}).map(
    ([type, counts]) => ({ type, created: counts.created ?? 0, referenced: counts.referenced ?? 0 }),
  );
  const edgeRows: EdgeCountRow[] = Object.entries(report?.edges_by_type ?? {}).map(
    ([type, counts]) => ({ type, created: counts.created ?? 0 }),
  );

  const entityColumns: TableColumn<EntityCountRow>[] = [
    { key: "type", header: "Entity type", render: (r) => <strong>{r.type}</strong> },
    { key: "created", header: "Would create", numeric: true, render: (r) => String(r.created) },
    { key: "referenced", header: "Would reference", numeric: true, render: (r) => String(r.referenced) },
  ];
  const edgeColumns: TableColumn<EdgeCountRow>[] = [
    { key: "type", header: "Edge type", render: (r) => <strong>{r.type}</strong> },
    { key: "created", header: "Would create", numeric: true, render: (r) => String(r.created) },
  ];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-16)",
        padding: "var(--sp-16)",
        height: "100%",
        overflow: "auto",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
        <Button onClick={onBack}>← Connect</Button>
        <h1 style={{ fontSize: "1.1em", margin: 0 }}>Verify{draft ? ` — ${draft.label}` : ""}</h1>
        <div style={{ flex: 1 }} />
        <Button onClick={() => void handleRunVerify()} variant="primary" disabled={running}>
          {running ? "Running…" : "Run verify"}
        </Button>
      </div>

      {error && (
        <div
          role="alert"
          style={{
            background: "var(--surface-raised)",
            border: "1px solid var(--border-strong)",
            borderRadius: "var(--r-panel)",
            padding: "var(--sp-8)",
          }}
        >
          {error}
        </div>
      )}

      {!report && !error && !running && (
        <p style={{ color: "var(--text-secondary)" }}>
          A dry run over the profiled sample. Nothing is written, but an entity set to reference
          an existing one is looked up in the live graph, at your own clearance. Nothing is
          published until Verify passes.
        </p>
      )}

      {report && (
        <>
          <p style={{ color: "var(--text-secondary)" }}>
            {report.rows_read} row(s) read
            {report.sample_is_whole_source ? " — the whole source." : " — the source has more rows than were verified."}
            {" · "}
            {report.rows_deduplicated} deduplicated
          </p>

          {report.values_masked && (
            <div
              role="status"
              style={{
                background: "var(--surface-raised)",
                border: "1px solid var(--border-strong)",
                borderRadius: "var(--r-panel)",
                padding: "var(--sp-8)",
                color: "var(--text-secondary)",
              }}
            >
              You aren't cleared for this source's handling marking, so every value this run
              would create is shown shape-masked — a referenced existing node's own values are
              unaffected, since your clearance already governs whether you can see it at all.
            </div>
          )}

          <div style={{ display: "flex", gap: "var(--sp-16)", flexWrap: "wrap" }}>
            {entityRows.length > 0 && (
              <Panel title="Entities">
                <Table columns={entityColumns} rows={entityRows} getRowId={(r) => r.type} />
              </Panel>
            )}
            {edgeRows.length > 0 && (
              <Panel title="Edges">
                <Table columns={edgeColumns} rows={edgeRows} getRowId={(r) => r.type} />
              </Panel>
            )}
          </div>

          {(report.rejections ?? []).length > 0 && (
            <Panel title="Rejected rows, by cause">
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {(report.rejections ?? []).map((group) => (
                  <li key={group.reason} style={{ marginBottom: "var(--sp-8)" }}>
                    <span style={{ color: "var(--warning)" }}>⚠</span> <strong>{group.count}</strong>{" "}
                    row(s) — {group.reason}
                    <ul style={{ margin: "var(--sp-4) 0 0 var(--sp-16)", padding: 0 }}>
                      {group.samples.map((s) => (
                        <li
                          key={s.row_index}
                          style={{ color: "var(--text-tertiary)", fontFamily: "var(--mono)" }}
                        >
                          row {s.row_index}: {s.sample}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title="The graph this recipe would produce">
            <div style={{ height: 480 }}>
              {workingSet && registry ? (
                <GlassCanvas
                  graph={workingSet.graph}
                  store={workingSet.store}
                  ontology={registry}
                  edgeTypes={edgeTypes}
                  // A dry run stores nothing: no case and no token, so the canvas asks the
                  // Conduit nothing (pictures, links among, files) about nodes that do not exist.
                  investigationId=""
                  apiBaseUrl={apiBaseUrl}
                  bearerToken=""
                />
              ) : (
                <p style={{ color: "var(--text-secondary)" }}>Loading the ontology…</p>
              )}
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
