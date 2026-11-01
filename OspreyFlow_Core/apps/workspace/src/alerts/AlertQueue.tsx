// The one alert queue and one alert's explanation (`06_DECISIONS.md` ADR-109 phase B, rulings 2
// and 3; ADR-133 decision 5 and stage (a)): every kind of alert the reader may see — typology,
// hotlist and monitor — each with its severity, who may see it, who has it and its age; what fired,
// on which entities, through which transactions — and the triage a member does: claim it, release
// it, give a case alert to a member, put it on the canvas, close it as a true or false positive with
// the reason. A true positive confirms the alert's node (rule 5); the server says which. The kind,
// severity and status filters are the server's: the Glass never hides a row it was sent.
import { useCallback, useEffect, useState } from "react";
import type { Alert, AlertAssignee, AlertExplanation, QueuedAlert } from "../../../../packages/schemas/generated";
import { Button, Select } from "../design/primitives";
import type { AccessLevel } from "../investigation/cases";
import {
  alertToCanvas,
  assignAlert,
  claimAlert,
  disposeAlert,
  explainAlert,
  listAssignees,
  listQueue,
  releaseAlert,
  type AlertsApi,
  type CanvasOutcome,
  type KindFilter,
  type QueueFilter,
  type SeverityFilter,
} from "./api";
import { money, nodeName, typologyLabel, when } from "./names";

export interface AlertQueueProps extends AlertsApi {
  level: AccessLevel | null;
  /** The signed-in account's id, to say "claimed by you". */
  accountId: string | null;
  onCanvas: (outcome: CanvasOutcome, nodeIds: string[]) => void;
}

const STATUS_WORDS: Record<string, string> = { open: "Open", claimed: "Claimed", closed: "Closed" };
const SEVERITY_WORDS: Record<string, string> = { high: "High", medium: "Medium", low: "Low" };

type Kind = "typology" | "hotlist" | "monitor";
type Audience = "case" | "team" | "owner";

/** A row's kind, severity and audience; a row from before ADR-133 is a medium case alert. */
function facts(row: Pick<QueuedAlert, "kind" | "severity" | "audience" | "team">) {
  return {
    kind: (row.kind ?? "typology") as Kind,
    severity: row.severity ?? "medium",
    audience: (row.audience ?? "case") as Audience,
    team: row.team ?? null,
  };
}

/** What the alert is called: a typology's name, or what kind of watch raised it. */
export function alertTitle(alert: Alert, kind: Kind): string {
  if (kind === "hotlist") return "Hotlist";
  if (kind === "monitor") return "Watched pattern";
  return typologyLabel(alert.typology);
}

/** Who may see it, in words (ADR-133 decision 5 and ruling 3). */
export function audienceWords(audience: Audience, team: string | null): string {
  if (audience === "case") return "The case team";
  if (audience === "team") return team ? `Shared with team ${team}` : "Shared with the owner's team";
  return "Only its owner";
}

/** How long it has waited, in words. */
export function ageWords(iso: string, now: Date = new Date()): string {
  const hours = Math.floor((now.getTime() - new Date(iso).getTime()) / 3_600_000);
  if (hours < 1) return "under an hour old";
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} old`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} old`;
}

/** Where an alert stands, in one sentence: "Claimed by you", "Closed as a true positive: …". */
export function statusSentence(alert: Alert, mine: boolean): string {
  if (alert.status === "closed") {
    const kind = alert.disposition === "false_positive" ? "a false" : "a true";
    return alert.disposition ? `Closed as ${kind} positive: ${alert.disposition_reason ?? ""}` : "Closed";
  }
  if (alert.status === "claimed" && alert.assignee) return `Claimed by ${mine ? "you" : alert.assignee}`;
  return STATUS_WORDS[alert.status ?? "open"] ?? "Open";
}

export function AlertQueue(props: AlertQueueProps) {
  const { apiBaseUrl, bearerToken, investigationId } = props;
  const [filter, setFilter] = useState<QueueFilter>("active");
  const [kind, setKind] = useState<KindFilter>("all");
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [rows, setRows] = useState<QueuedAlert[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const reload = useCallback(() => {
    setProblem(null);
    listQueue({ apiBaseUrl, bearerToken, investigationId }, { status: filter, kind, severity })
      .then(setRows)
      .catch((e: Error) => setProblem(e.message));
  }, [apiBaseUrl, bearerToken, investigationId, filter, kind, severity]);

  useEffect(reload, [reload]);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 1fr) 2fr", gap: "var(--sp-16)", minHeight: 0 }}>
      <section aria-label="Alert queue" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)", minHeight: 0 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)" }}>
          <label className="label" style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
            Show
            <Select aria-label="Which alerts" value={filter} onChange={(e) => setFilter(e.target.value as QueueFilter)}>
              <option value="active">Open and claimed</option>
              <option value="closed">Closed</option>
              <option value="all">All</option>
            </Select>
          </label>
          <label className="label" style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
            Kind
            <Select aria-label="Kind of alert" value={kind} onChange={(e) => setKind(e.target.value as KindFilter)}>
              <option value="all">Every kind</option>
              <option value="typology">Rules</option>
              <option value="hotlist">Hotlists</option>
              <option value="monitor">Watched patterns</option>
            </Select>
          </label>
          <label className="label" style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
            Severity
            <Select aria-label="Severity" value={severity} onChange={(e) => setSeverity(e.target.value as SeverityFilter)}>
              <option value="all">Any</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </Select>
          </label>
        </div>
        {problem && <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>}
        {rows !== null && rows.length === 0 && <p className="label">No alerts here.</p>}
        {rows !== null && rows.length > 0 && (
          <p className="label">
            {rows.length} alert{rows.length === 1 ? "" : "s"} you can see.
          </p>
        )}
        <ul style={{ listStyle: "none", margin: 0, padding: 0, overflowY: "auto" }}>
          {(rows ?? []).map((row) => {
            const f = facts(row);
            const title = alertTitle(row.alert, f.kind);
            return (
              <li key={row.alert.id} style={{ borderBottom: "1px solid var(--border-subtle)", padding: "var(--sp-4) 0" }}>
                {/* The button's name is its own visible words, with the hidden words that make them a
                    sentence (WCAG 2.5.3): "Open alert: High severity, Hotlist — <what it found>". */}
                <button
                  type="button"
                  className="btn btn--quiet"
                  aria-pressed={openId === row.alert.id}
                  onClick={() => setOpenId(row.alert.id)}
                  style={{ width: "100%", textAlign: "left", display: "block", padding: "var(--sp-8)", height: "auto", whiteSpace: "normal" }}
                >
                  <span className="visually-hidden">Open alert: </span>
                  <span className={`severity severity--${f.severity}`}>{SEVERITY_WORDS[f.severity]}</span>
                  <span className="visually-hidden"> severity, </span>{" "}
                  <span className="value">{title}</span>
                  <span className="visually-hidden"> — </span>
                  <br />
                  <span className="label">{row.summary}</span>
                </button>
                <p className="label" style={{ margin: 0, padding: "0 var(--sp-8)" }}>
                  {STATUS_WORDS[row.alert.status ?? "open"]}
                  {row.alert.assignee ? ` · ${row.alert.assignee === props.accountId ? "you" : row.alert.assignee}` : ""}
                  {` · ${audienceWords(f.audience, f.team)} · ${ageWords(row.alert.created_at)} · ${when(row.alert.created_at)}`}
                </p>
              </li>
            );
          })}
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
  const f = facts(why);
  const canTriage = level === "editor" || level === "author";
  const closed = alert.status === "closed";
  const mine = alert.assignee === props.accountId;

  return (
    <section aria-label="What fired this alert" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)", overflowY: "auto" }}>
      <h3 className="value" style={{ margin: 0 }}>{alertTitle(alert, f.kind)}</h3>
      <p className="label" style={{ margin: 0 }}>
        {`${alertTitle(alert, f.kind)} · ${SEVERITY_WORDS[f.severity]} severity · ${audienceWords(f.audience, f.team)}`}
      </p>
      <p style={{ margin: 0 }}>{why.summary}</p>
      {f.kind === "typology" && (
        <p className="label" style={{ margin: 0 }}>
          {`Raised ${alert.trigger === "pre_commit" ? "as the data loaded (before it was committed)" : "after the data loaded"}`}
          {alert.window ? ` · ${when(alert.window.valid_from)} to ${when(alert.window.valid_to ?? alert.window.valid_from)}` : ""}
        </p>
      )}
      {f.kind === "typology" && alert.alert_node_id === null && (
        <p className="label" style={{ color: "var(--warning)", margin: 0 }}>
          This alert has no node on the graph: what it concerns is held under markings no single marking can cover.
        </p>
      )}
      {(why.transactions ?? []).length === 0 ? (
        // A KYC alert cites parties, not money: the applicant, its owner, the listed party.
        <ul aria-label="What this alert concerns" style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
          {nodes
            .filter((n) => n.type !== "Alert")
            .map((n) => (
              <li key={n.id}>{`${nodeName(n)} · ${n.type}`}</li>
            ))}
        </ul>
      ) : (
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
      )}
      <p className="label" style={{ margin: 0 }}>
        {statusSentence(alert, mine)}
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
      {canTriage && !closed && f.audience === "case" && (
        <GiveTo api={api} alertId={alertId} busy={busy} act={act} />
      )}
      {canTriage && !closed && f.audience !== "case" && (
        <p className="label" style={{ margin: 0 }}>
          An alert shared with a team, or its owner&apos;s alone, is claimed by someone who can see it; it is not given to another person.
        </p>
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

/** ADR-133 stage (a): give a case alert to one of the case's Editors or Authors, by name. */
function GiveTo(props: {
  api: AlertsApi;
  alertId: string;
  busy: boolean;
  act: (what: () => Promise<unknown>, words: string) => Promise<void>;
}) {
  const { api, alertId } = props;
  const [people, setPeople] = useState<AlertAssignee[]>([]);
  const [chosen, setChosen] = useState("");
  useEffect(() => {
    listAssignees(api)
      .then(setPeople)
      .catch(() => setPeople([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken, api.investigationId]);
  if (people.length === 0) return null;
  const name = (id: string) => people.find((p) => p.id === id)?.name ?? id;
  return (
    <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "flex-end", flexWrap: "wrap" }}>
      <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
        Give to
        <Select aria-label="Give this alert to" value={chosen} onChange={(e) => setChosen(e.target.value)}>
          <option value="">Choose a member…</option>
          {people.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name ?? p.id}
            </option>
          ))}
        </Select>
      </label>
      <Button
        disabled={props.busy || !chosen}
        onClick={() => void props.act(() => assignAlert(api, alertId, chosen), `Given to ${name(chosen)}.`)}
      >
        Give
      </Button>
    </div>
  );
}
