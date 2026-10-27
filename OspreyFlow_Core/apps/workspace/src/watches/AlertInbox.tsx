// The alert inbox — `02_GLASS_FRONTEND.md` §3.3: "Every alert names the rule that fired and shows
// the evidence... Alerts carry the matched identifier, the triggering document, and a one-click
// jump into a pre-populated investigation." `watch_routes.py`'s own `AlertView` already redacts
// server-side (`referent_node_ids` is authoritatively `[]` whenever a `notify_stub` alert or an
// unavailable-evidence `full` alert is serialised) — `AlertRow` below renders exactly what the
// wire payload says and reconstructs nothing, so the redaction the server already did cannot be
// undone by a renderer trying to be helpful.
//
// Errors surface as an inline banner, not `ActionErrorOverlay` — `HotlistPanel.tsx`'s own doc
// comment has the full reasoning, identical here.
import { useEffect, useState } from "react";

import { Button } from "../design/primitives/Button";
import { Panel } from "../design/primitives/Panel";
import {
  type AlertJumpResult,
  type AlertView,
  type FiredFile,
  type FiredOn,
  isScheduleNotice,
  jumpAlert,
  listAlerts,
} from "./api";

const COUNT = new Intl.NumberFormat("en-GB");
const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

/** ADR-130: an alert is named by what it is, never by its rule id (`hotlist:<id>`). */
function heading(alert: AlertView): string {
  if (alert.rule_id.startsWith("hotlist:")) return "Hotlist alert";
  if (alert.rule_id.startsWith("monitor:")) return "Monitor alert";
  return "Alert";
}

function fileText(file: FiredFile): string {
  if (file.row != null) return `${file.name}, row ${COUNT.format(file.row)}`;
  if (file.records != null) {
    return `${file.name}, ${COUNT.format(file.records)} ${file.records === 1 ? "record" : "records"}`;
  }
  const rows = file.rows ?? 0;
  return `${file.name}, ${COUNT.format(rows)} ${rows === 1 ? "row" : "rows"}`;
}

/** "a.csv, row 3; b.csv, 2,013 rows; and 3 more files" — the files past five are said, not cut. */
function fromText(fired: FiredOn): string {
  const parts = fired.files.map(fileText);
  if (fired.more_files > 0) {
    parts.push(`and ${COUNT.format(fired.more_files)} more file${fired.more_files === 1 ? "" : "s"}`);
  }
  return parts.join("; ");
}

export interface AlertRowProps {
  alert: AlertView;
  onJump: (alertId: string) => void;
  jumping: boolean;
}

/** ADR-110 decision 10: a scheduled run that failed or was refused, told to its owner in words.
 * It names no entity and has no case to jump into, so it is read, not jumped. */
function ScheduleNoticeRow({ alert }: { alert: AlertView }) {
  return (
    <li style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)", padding: "var(--sp-8) 0",
                 borderBottom: "1px solid var(--border-subtle)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className="value">Scheduled run</span>
        <span className="label">{new Date(alert.created_at).toLocaleString()}</span>
      </div>
      <p className="label" style={{ margin: 0 }}>{alert.words}</p>
    </li>
  );
}

export function AlertRow({ alert, onJump, jumping }: AlertRowProps) {
  if (isScheduleNotice(alert)) return <ScheduleNoticeRow alert={alert} />;
  const hasReferents = alert.mode === "full" && alert.referent_node_ids.length > 0;
  // A hotlist alert whose evidence was readable when the list was read but whose node had gone by the
  // time it was described (two reads, a node revoked between) is unavailable too, and nothing can
  // be jumped into.
  const vanished =
    alert.mode === "full" &&
    hasReferents &&
    alert.evidence_available &&
    alert.rule_id.startsWith("hotlist:") &&
    (alert.fired_on == null || alert.fired_on.length === 0);
  const unavailable = alert.mode === "full" && (!hasReferents || vanished);
  return (
    <li
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-4)",
        padding: "var(--sp-8) 0",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className="value">{heading(alert)}</span>
        <span className="label">{new Date(alert.created_at).toLocaleString()}</span>
      </div>
      {alert.mode === "notify_stub" && (
        <p className="label">A match fired — no evidence visible to you.</p>
      )}
      {alert.hotlist && (
        <p className="label" style={{ margin: 0 }}>
          {`Hotlist: ${alert.hotlist.identifier}${alert.hotlist.kept_as_written ? " (kept as written)" : ""}`}
          {` · review by ${DAY.format(new Date(alert.hotlist.review_date))}`}
        </p>
      )}
      {alert.mode === "full" && hasReferents && !vanished && (alert.fired_on ?? []).map((fired, index) => (
        <div key={index} style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
          <span className="value">
            {fired.sources_withheld
              ? `Matched: ${fired.type} ${fired.label} \u2014 its sources are in data this case does not read`
              : `Matched: ${fired.type} ${fired.label}`}
          </span>
          {!fired.sources_withheld && fired.files.length > 0 && <span className="label">{`From: ${fromText(fired)}`}</span>}
        </div>
      ))}
      {unavailable && (
        <p className="label" style={{ color: "var(--warning)" }}>
          Evidence no longer available.
        </p>
      )}
      <Button onClick={() => onJump(alert.id)} disabled={jumping || unavailable}>
        {jumping ? "Jumping…" : "Jump into investigation"}
      </Button>
    </li>
  );
}

export interface JumpResultSummaryProps {
  result: AlertJumpResult;
  onOpen: (investigationId: string) => void;
}

/** ADR-124 decision 1: the summary says what was added and nothing of what could not be read — no
 * count of it, however it is framed. */
export function JumpResultSummary({ result, onOpen }: JumpResultSummaryProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
      <p className="value" data-testid="jump-seeded-summary">
        {result.seeded_count} entit{result.seeded_count === 1 ? "y" : "ies"} added to the new
        investigation.
      </p>
      <Button variant="primary" onClick={() => onOpen(result.investigation.id)}>
        Open investigation
      </Button>
    </div>
  );
}

export interface AlertInboxProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** ADR-099 Amendment 3: the case whose datasets these are. */
  investigationId: string;
  onOpenInvestigation: (investigationId: string) => void;
}

export function AlertInbox({ apiBaseUrl, bearerToken, investigationId, onOpenInvestigation }: AlertInboxProps) {
  const [alerts, setAlerts] = useState<AlertView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [jumpingId, setJumpingId] = useState<string | null>(null);
  const [jumpResult, setJumpResult] = useState<AlertJumpResult | null>(null);

  useEffect(() => {
    listAlerts(apiBaseUrl, bearerToken, investigationId)
      .then(setAlerts)
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleJump(alertId: string): Promise<void> {
    setError(null);
    setJumpingId(alertId);
    try {
      setJumpResult(await jumpAlert(apiBaseUrl, bearerToken, investigationId, alertId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setJumpingId(null);
    }
  }

  return (
    <Panel title="Alert inbox" className="alert-inbox">
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
        {error && (
          <p role="alert" style={{ color: "var(--error)" }}>
            {error}
          </p>
        )}
        {jumpResult && (
          <JumpResultSummary
            result={jumpResult}
            onOpen={(investigationId) => {
              onOpenInvestigation(investigationId);
              setJumpResult(null);
            }}
          />
        )}
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {alerts.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              onJump={(id) => void handleJump(id)}
              jumping={jumpingId === alert.id}
            />
          ))}
        </ul>
      </div>
    </Panel>
  );
}
