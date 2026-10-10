// The case team's alert queue and one alert's explanation (`06_DECISIONS.md` ADR-109 phase B,
// rulings 2 and 3): what fired, on which entities, through which transactions — and the triage a
// member does: claim it, release it, put it on the canvas, close it as a true or false positive
// with the reason. A true positive confirms the alert's node (rule 5); the server says which.
import { useCallback, useEffect, useState } from "react";
import type { AlertExplanation, QueuedAlert } from "../../../../packages/schemas/generated";
import { Button, Select } from "../design/primitives";
import type { AccessLevel } from "../investigation/cases";
import {
  alertToCanvas,
  claimAlert,
  disposeAlert,
  explainAlert,
  listQueue,
  releaseAlert,
  type AlertsApi,
  type CanvasOutcome,
  type QueueFilter,
} from "./api";
import { money, nodeName, typologyLabel, when } from "./names";

export interface AlertQueueProps extends AlertsApi {
  level: AccessLevel | null;
  /** The signed-in account's id, to say "claimed by you". */
  accountId: string | null;
  onCanvas: (outcome: CanvasOutcome, nodeIds: string[]) => void;
}

const STATUS_WORDS: Record<string, string> = { open: "Open", claimed: "Claimed", closed: "Closed" };

export function AlertQueue(props: AlertQueueProps) {
  const { apiBaseUrl, bearerToken, investigationId } = props;
  const [filter, setFilter] = useState<QueueFilter>("active");
  const [rows, setRows] = useState<QueuedAlert[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const reload = useCallback(() => {
    setProblem(null);
    listQueue({ apiBaseUrl, bearerToken, investigationId }, filter)
      .then(setRows)
      .catch((e: Error) => setProblem(e.message));
  }, [apiBaseUrl, bearerToken, investigationId, filter]);

  useEffect(reload, [reload]);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 1fr) 2fr", gap: "var(--sp-16)", minHeight: 0 }}>
      <section aria-label="Alert queue" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)", minHeight: 0 }}>
        <label className="label" style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
          Show
          <Select aria-label="Which alerts" value={filter} onChange={(e) => setFilter(e.target.value as QueueFilter)}>
            <option value="active">Open and claimed</option>
            <option value="closed">Closed</option>
            <option value="all">All</option>
          </Select>
        </label>
        {problem && <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>}
        {rows !== null && rows.length === 0 && <p className="label">No alerts here.</p>}
        {rows !== null && rows.length > 0 && (
          <p className="label">
            {rows.length} alert{rows.length === 1 ? "" : "s"} you can see.
          </p>
        )}
        <ul style={{ listStyle: "none", margin: 0, padding: 0, overflowY: "auto" }}>
          {(rows ?? []).map((row) => (
            <li key={row.alert.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
              <button
                type="button"
                className="btn btn--quiet"
                aria-pressed={openId === row.alert.id}
                aria-label={`Open alert: ${typologyLabel(row.alert.typology)} — ${row.summary}`}
                onClick={() => setOpenId(row.alert.id)}
                style={{ width: "100%", textAlign: "left", display: "flex", flexDirection: "column", gap: "var(--sp-4)", padding: "var(--sp-8)" }}
              >
                <span style={{ display: "flex", justifyContent: "space-between", gap: "var(--sp-8)" }}>
                  <span className="value">{typologyLabel(row.alert.typology)}</span>
                  <span className="label">
                    {STATUS_WORDS[row.alert.status ?? "open"]}
                    {row.alert.assignee ? ` · ${row.alert.assignee === props.accountId ? "you" : row.alert.assignee}` : ""}
                  </span>
                </span>
                <span className="label">{row.summary}</span>
                <span className="label">{when(row.alert.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
      {openId ? (
        <AlertDetail
          key={openId}
          {...props}
          alertId={openId}
          onChanged={reload}
        />
      ) : (
        <p className="label">Choose an alert to see what fired it.</p>
      )}
    </div>
  );
}

interface AlertDetailProps extends AlertQueueProps {
  alertId: string;
  onChanged: () => void;
}

function AlertDetail(props: AlertDetailProps) {
  const api: AlertsApi = props;
  const { alertId, level } = props;
  const [why, setWhy] = useState<AlertExplanation | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    explainAlert(api, alertId)
      .then(setWhy)
      .catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alertId, props.apiBaseUrl, props.bearerToken, props.investigationId]);
  useEffect(load, [load]);

  const act = async (what: () => Promise<unknown>, words: string) => {
    setBusy(true);
    setProblem(null);
    try {
      await what();
      setSaid(words);
      props.onChanged();
      load();
    } catch (e) {
      setProblem((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (problem && !why) return <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>;
  if (!why) return <p className="label">Opening…</p>;

  const nodes = why.nodes ?? [];
  const names = new Map(nodes.map((n) => [n.id, nodeName(n)]));
  const alert = why.alert;
  const canTriage = level === "editor" || level === "author";
  const closed = alert.status === "closed";
  const mine = alert.assignee === props.accountId;

  return (
    <section aria-label="What fired this alert" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)", overflowY: "auto" }}>
      <h3 className="value" style={{ margin: 0 }}>{typologyLabel(alert.typology)}</h3>
      <p style={{ margin: 0 }}>{why.summary}</p>
      <p className="label" style={{ margin: 0 }}>
        Raised {alert.trigger === "pre_commit" ? "as the data loaded (before it was committed)" : "after the data loaded"} ·{" "}
        {alert.window ? `${when(alert.window.valid_from)} to ${when(alert.window.valid_to ?? alert.window.valid_from)}` : ""}
      </p>
      {alert.alert_node_id === null && (
        <p className="label" style={{ color: "var(--warning)", margin: 0 }}>
          This alert has no node on the graph: what it concerns is held under markings no single marking can cover.
        </p>
      )}
      <table className="table" aria-label="Transactions this alert cites">
        <thead>
          <tr>
            <th>When</th>
            <th>From</th>
            <th>To</th>
            <th style={{ textAlign: "right" }}>Amount</th>
          </tr>
        </thead>
        <tbody>
          {(why.transactions ?? []).map((t) => (
            <tr key={t.event_id}>
              <td>{when(t.occurred_at)}</td>
              <td>{names.get(t.source_id) ?? "—"}</td>
              <td>{names.get(t.target_id) ?? "—"}</td>
              <td style={{ textAlign: "right" }}>{money(t.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="label" style={{ margin: 0 }}>
        {STATUS_WORDS[alert.status ?? "open"]}
        {alert.assignee ? `, ${mine ? "claimed by you" : `claimed by ${alert.assignee}`}` : ""}
        {closed && alert.disposition
          ? ` as a ${alert.disposition === "true_positive" ? "true" : "false"} positive: ${alert.disposition_reason ?? ""}`
          : ""}
      </p>
      {said && <p role="status" className="label">{said}</p>}
      {problem && <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>}
      {canTriage && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)" }}>
          <Button
            disabled={busy}
            onClick={() =>
              void (async () => {
                setBusy(true);
                setProblem(null);
                try {
                  const outcome = await alertToCanvas(api, alertId);
                  props.onCanvas(outcome, nodes.map((n) => n.id));
                } catch (e) {
                  setProblem((e as Error).message);
                } finally {
                  setBusy(false);
                }
              })()
            }
          >
            Show on the canvas
          </Button>
          {!closed && alert.status === "open" && (
            <Button disabled={busy} onClick={() => void act(() => claimAlert(api, alertId), "You have claimed this alert.")}>
              Claim
            </Button>
          )}
          {!closed && alert.status === "claimed" && mine && (
            <Button disabled={busy} onClick={() => void act(() => releaseAlert(api, alertId), "Released for someone else.")}>
              Release
            </Button>
          )}
        </div>
      )}
      {canTriage && !closed && (
        <fieldset style={{ border: "1px solid var(--border-subtle)", padding: "var(--sp-12)", display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
          <legend className="label">Close this alert</legend>
          <label className="label" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
            Reason (required)
            <textarea
              className="input"
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              aria-label="Reason for closing"
            />
          </label>
          <div style={{ display: "flex", gap: "var(--sp-8)" }}>
            <Button
              variant="primary"
              disabled={busy || !reason.trim()}
              onClick={() =>
                void act(
                  () => disposeAlert(api, alertId, { disposition: "true_positive", reason: reason.trim() }),
                  "Closed as a true positive; its node is now confirmed.",
                )
              }
            >
              Close as true positive
            </Button>
            <Button
              disabled={busy || !reason.trim()}
              onClick={() =>
                void act(
                  () => disposeAlert(api, alertId, { disposition: "false_positive", reason: reason.trim() }),
                  "Closed as a false positive; its node stays a suggestion.",
                )
              }
            >
              Close as false positive
            </Button>
          </div>
        </fieldset>
      )}
    </section>
  );
}
