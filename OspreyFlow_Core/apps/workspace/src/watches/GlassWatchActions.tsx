// What the Glass makes for Rules and Monitoring, where people already look (`06_DECISIONS.md`
// ADR-146 decisions 4 and 7):
// - *Save as a watch* on a saved query pattern: a watched pattern of the case's dataset, run by every
//   load into it and on its own schedule (daily by default, G16), matched as its maker alone, so it
//   alerts only on what they may see (rule 3);
// - *Watch for this* on an entity that carries an identifier: a hotlist entry for it, kept with the
//   watches, whose alert under `strict` says nothing of a match its owner may not see (ADR-038);
// - *Raise an alert…* on query results and a selection: a title, a severity, a reason and where it
//   goes — this case, or the case's dataset (its home case's queue, closed by the home case's
//   Authors). The Conduit refuses a case or dataset the raiser may not write, an item they may not
//   read, and a dataset alert citing a drawn item, in words shown here.
// Each is kept in *What raises alerts* or the one queue; the Glass works neither.
import { useEffect, useState } from "react";
import type { Node } from "../../../../packages/schemas/generated";
import { raiseAlert } from "../alerts/api";
import { Button, Input, Select } from "../design/primitives";
import { listCases } from "../investigation/cases";
import { createHotlist, createMonitor } from "./api";

export interface GlassApi {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
}

/** *Save as a watch*: the saved pattern watched for the case's dataset. */
export function SaveAsWatch(props: GlassApi & { patternId: string | null }) {
  const [said, setSaid] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  if (!props.patternId) return null;
  const patternId = props.patternId;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
      <Button
        type="button"
        onClick={() =>
          void createMonitor(props.apiBaseUrl, props.bearerToken, props.investigationId, { pattern_id: patternId })
            .then(() => {
              setProblem(null);
              setSaid("Saved as a watch: it runs as data loads and daily, and is kept in Rules and Monitoring › What raises alerts.");
            })
            .catch((e: Error) => setProblem(e.message))
        }
      >
        Save as a watch
      </Button>
      {said && <p role="status" className="label">{said}</p>}
      {problem && <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>}
    </div>
  );
}

/** The identifier an entity is watched by, if it carries one. */
export function watchableIdentifier(node: Pick<Node, "properties">): string | null {
  const value = node.properties?.["value_normalised"];
  return typeof value === "string" && value.trim() ? value : null;
}

/** *Watch for this*: a hotlist entry for the entity's identifier, reviewed in 90 days. */
export function WatchForThis(props: GlassApi & { node: Pick<Node, "id" | "properties"> }) {
  const [said, setSaid] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const identifier = watchableIdentifier(props.node);
  if (!identifier) return null;
  const review = new Date(Date.now() + 90 * 86_400_000).toISOString().slice(0, 10);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
      <Button
        type="button"
        onClick={() =>
          void createHotlist(props.apiBaseUrl, props.bearerToken, props.investigationId, { identifier, review_date: review })
            .then(() => {
              setProblem(null);
              setSaid(`Watching for ${identifier}: you are alerted when it appears in data you may see. Review it by ${review}.`);
            })
            .catch((e: Error) => setProblem(e.message))
        }
      >
        Watch for this
      </Button>
      {said && <p role="status" className="label">{said}</p>}
      {problem && <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>}
    </div>
  );
}

export interface RaiseAlertProps extends GlassApi {
  nodeIds: string[];
  edgeIds?: string[];
  /** What found them, in words: the query or the question. */
  foundBy?: string | null;
}

/** *Raise an alert…*: the form, opened from query results or a selection. */
export function RaiseAlert(props: RaiseAlertProps) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [severity, setSeverity] = useState<"low" | "medium" | "high">("medium");
  const [reason, setReason] = useState("");
  const [to, setTo] = useState<"case" | "dataset">("case");
  const [datasets, setDatasets] = useState<{ id: string; name: string }[]>([]);
  const [dataset, setDataset] = useState("");
  const [said, setSaid] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    listCases(props.apiBaseUrl, props.bearerToken)
      .then((cases) => {
        const c = cases.find((x) => x.id === props.investigationId);
        const ids = c?.dataset_ids ?? [];
        const names = c?.datasets ?? [];
        const found = ids.map((id, i) => ({ id, name: names[i] ?? id }));
        setDatasets(found);
        setDataset((d) => d || (found[0]?.id ?? ""));
      })
      .catch(() => setDatasets([]));
  }, [open, props.apiBaseUrl, props.bearerToken, props.investigationId]);
  if (props.nodeIds.length === 0) return null;
  if (!open) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
        <Button type="button" onClick={() => setOpen(true)}>
          Raise an alert…
        </Button>
        {said && <p role="status" className="label">{said}</p>}
      </div>
    );
  }
  const ready = title.trim() && reason.trim() && (to === "case" || dataset);
  return (
    <fieldset style={{ border: "1px solid var(--border-subtle)", padding: "var(--sp-12)", display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
      <legend className="label">{`Raise an alert on ${props.nodeIds.length} item${props.nodeIds.length === 1 ? "" : "s"}`}</legend>
      <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
        Title
        <Input aria-label="Title of the alert" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
      </label>
      <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
        Severity
        <Select aria-label="Severity of the alert" value={severity} onChange={(e) => setSeverity(e.target.value as typeof severity)}>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </Select>
      </label>
      <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
        Why, in words (required)
        <textarea className="input" rows={2} aria-label="Why, in words: the reason for the alert" value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
        Goes to
        <Select aria-label="Where the alert goes" value={to} onChange={(e) => setTo(e.target.value as typeof to)}>
          <option value="case">This case: its members see it</option>
          <option value="dataset">The dataset: everyone with a case on it sees it</option>
        </Select>
      </label>
      {to === "dataset" && datasets.length > 1 && (
        <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
          Dataset
          <Select aria-label="Which dataset" value={dataset} onChange={(e) => setDataset(e.target.value)}>
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
        </label>
      )}
      {to === "dataset" && (
        <p className="label" style={{ margin: 0 }}>
          A dataset alert may cite only the dataset&apos;s own items: an item drawn in this case is refused. Promote it first, or raise the alert to this case.
        </p>
      )}
      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
        <Button
          variant="primary"
          disabled={busy || !ready}
          onClick={() =>
            void (async () => {
              setBusy(true);
              setProblem(null);
              try {
                await raiseAlert(props, {
                  title: title.trim(),
                  severity,
                  reason: reason.trim(),
                  to,
                  dataset_id: to === "dataset" ? dataset : null,
                  node_ids: props.nodeIds as [string, ...string[]],
                  edge_ids: props.edgeIds ?? [],
                  found_by: props.foundBy ?? null,
                });
                setSaid(to === "dataset" ? "Raised to the dataset: it is in its home case's queue." : "Raised to this case: it is in the case's queue.");
                setOpen(false);
              } catch (e) {
                setProblem((e as Error).message);
              } finally {
                setBusy(false);
              }
            })()
          }
        >
          Raise the alert
        </Button>
        <Button type="button" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
      {problem && <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>}
    </fieldset>
  );
}
