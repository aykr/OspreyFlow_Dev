// *Preview* on one node of the pipeline (ADR-140 decision 14; ADR-108 Amendment 6.3; redesign brief
// §6): today's dry run up to that node, shown as the node's table, or, on Map and Load, as the graph
// it would make. It writes nothing. A source or profile node reads the Map sample rows (row 0 on,
// until the last row or `PREVIEW_ROWS`); a Map or Load node reads `preview-graph`, the dry run Test
// runs, which marks nothing, so a Preview never counts as Test or satisfies Deploy (the review of
// L1.2 found the first build calling `verify` itself, which marks the draft verified).
// Both read with the person's own token, so the server's own masking and access checks are the
// Preview's: a row the person may not read is shape-masked there, never here
// (`tests/ingest/test_node_preview_access.py` proves the sequence below, rule 4). Until phase 7's
// staging steps, nothing lies between a source and Map, so "up to that node" is the source's rows.
import { useState } from "react";

import type {
  EdgeTypeDef,
  MapSampleRow,
  PipelineNode,
  VerifyReport,
} from "../../../../../packages/schemas/generated";
import { GlassCanvas } from "../../canvas/GlassCanvas";
import { Button } from "../../design/primitives/Button";
import { Table, type TableColumn } from "../../design/primitives/Table";
import { OntologyRegistry } from "../../ontology/schema";
import { createWorkingSet, type WorkingSet } from "../../workingset/store";
import { ProfileError, fetchOntologySchema, fetchSampleRow, previewGraph } from "../api";

/** The most rows a table Preview reads. The one place this number is written:
 * `tests/ingest/test_node_preview_access.py` reads it from this line. */
export const PREVIEW_ROWS = 10;

const PREVIEW_ERRORS: Record<string, string> = {
  recipe_not_ready_for_profile: "Choose this pipeline's source first: there is nothing to preview yet.",
  row_template_missing: "Map has nothing saved yet, so there is no graph to preview. Open the map editor and save it.",
  connector_not_available: "This source's connector has no reader yet, so it cannot be previewed.",
  source_unreadable: "The source could not be read. Check it is still where the source says.",
  source_handling_incomplete: "This source's marking is incomplete, so it cannot be previewed.",
  ontology_violation: "The map does not match the target model. Open the map editor and check the element named.",
  right_required: "A graph Preview runs Test's dry run, so it needs the right to test pipelines, which you do not hold.",
};

function words(err: unknown): string {
  if (err instanceof ProfileError) return PREVIEW_ERRORS[err.code] ?? err.message;
  return err instanceof Error ? err.message : "The preview could not be read.";
}

export type PreviewShape = "table" | "graph" | "none";

/** What a node's Preview shows: the rows it reads, the graph it makes, or nothing yet. */
export function previewShape(kind: string): PreviewShape {
  if (kind === "source" || kind === "profile") return "table";
  if (kind === "map" || kind === "load") return "graph";
  return "none";
}

export interface NodePreviewProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  recipeId: string;
  node: PipelineNode;
}

export function NodePreview({ apiBaseUrl, bearerToken, investigationId, recipeId, node }: NodePreviewProps) {
  const shape = previewShape(node.kind);
  const [rows, setRows] = useState<MapSampleRow[] | null>(null);
  const [report, setReport] = useState<VerifyReport | null>(null);
  const [graph, setGraph] = useState<{ ws: WorkingSet; registry: OntologyRegistry; edgeTypes: EdgeTypeDef[] } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function previewTable() {
    const read: MapSampleRow[] = [];
    for (let index = 0; index < PREVIEW_ROWS; index++) {
      const row = await fetchSampleRow(apiBaseUrl, bearerToken, investigationId, recipeId, index);
      read.push(row);
      if (row.is_last_row) break;
    }
    setRows(read);
  }

  async function previewTheGraph() {
    const [result, schema] = await Promise.all([
      previewGraph(apiBaseUrl, bearerToken, investigationId, recipeId),
      fetchOntologySchema(apiBaseUrl, bearerToken),
    ]);
    const ws = createWorkingSet();
    for (const n of result.nodes ?? []) ws.graph.addNode(n.id, { data: n });
    for (const e of result.edges ?? []) ws.graph.addEdgeWithKey(e.id, e.source, e.target, { data: e });
    setReport(result);
    setGraph({ ws, registry: new OntologyRegistry(schema), edgeTypes: schema.edge_types });
  }

  async function run() {
    setBusy(true);
    setProblem(null);
    try {
      await (shape === "table" ? previewTable() : previewTheGraph());
    } catch (err: unknown) {
      setProblem(words(err));
    } finally {
      setBusy(false);
    }
  }

  if (shape === "none") {
    return (
      <p className="label" style={{ margin: 0 }}>
        {node.kind === "extract" || node.kind === "enrich"
          ? "This step has no preview yet: Test the whole pipeline to see what it finds."
          : "This step makes no rows of its own, so it has nothing to preview."}
      </p>
    );
  }

  const columnNames = [...new Set((rows ?? []).flatMap((r) => Object.keys(r.values)))];
  const columns: TableColumn<MapSampleRow>[] = [
    { key: "#", header: "Row", numeric: true, render: (r) => String(r.row_index + 1) },
    ...columnNames.map((name) => ({ key: name, header: name, render: (r: MapSampleRow) => r.values[name] ?? "" })),
  ];
  const masked = (rows ?? []).some((r) => r.values_masked);
  const created = Object.values(report?.entities_by_type ?? {}).reduce((sum, c) => sum + (c.created ?? 0), 0);
  const referenced = Object.values(report?.entities_by_type ?? {}).reduce((sum, c) => sum + (c.referenced ?? 0), 0);
  const links = Object.values(report?.edges_by_type ?? {}).reduce((sum, c) => sum + (c.created ?? 0), 0);

  return (
    <section aria-label={`Preview of ${node.label}`} style={{ display: "grid", gap: "var(--sp-8)", minWidth: 0 }}>
      <p className="label" style={{ margin: 0 }}>
        {shape === "table"
          ? "A dry run up to this step: the rows it reads, at your own clearance. Nothing is written."
          : "A dry run up to this step: the graph it would make, at your own clearance. Nothing is written."}
      </p>
      <div>
        <Button disabled={busy} onClick={() => void run()}>
          {busy ? "Previewing…" : rows || report ? "Preview again" : "Run preview"}
        </Button>
      </div>
      {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
      {rows && (
        <>
          <p role="status" style={{ margin: 0 }}>
            {`A sample: the first ${rows.length} row${rows.length === 1 ? "" : "s"}${
              rows.length === PREVIEW_ROWS && !rows[rows.length - 1]!.is_last_row ? ", and the source has more" : ""
            }.`}
            {masked && " Some values are masked to their shape: you are not cleared for the rows' marking."}
          </p>
          <div style={{ overflowX: "auto" }} tabIndex={0} role="region" aria-label="Preview rows">
            <Table columns={columns} rows={rows} getRowId={(r) => String(r.row_index)} />
          </div>
        </>
      )}
      {report && (
        <>
          <p role="status" style={{ margin: 0 }}>
            {`From a sample of ${report.rows_read} rows: ${created} would be created, ${referenced} referenced, ${links} links; ${(
              report.rejections ?? []
            ).reduce((sum, g) => sum + g.count, 0)} rows rejected.`}
          </p>
          <div style={{ height: 280, border: "1px solid var(--border-subtle)", borderRadius: "var(--r-panel)" }}>
            {graph && (
              <GlassCanvas
                graph={graph.ws.graph}
                store={graph.ws.store}
                ontology={graph.registry}
                edgeTypes={graph.edgeTypes}
                // A dry run stores nothing: no case and no token, as on Test.
                investigationId=""
                apiBaseUrl={apiBaseUrl}
                bearerToken=""
              />
            )}
          </div>
        </>
      )}
    </section>
  );
}
