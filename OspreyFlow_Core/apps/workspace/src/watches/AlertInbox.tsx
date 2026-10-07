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
import { type AlertJumpResult, type AlertView, jumpAlert, listAlerts } from "./api";

export interface AlertRowProps {
  alert: AlertView;
  onJump: (alertId: string) => void;
  jumping: boolean;
}

export function AlertRow({ alert, onJump, jumping }: AlertRowProps) {
  const hasReferents = alert.mode === "full" && alert.referent_node_ids.length > 0;
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
        <span className="value">{alert.rule_id}</span>
        <span className="label">{new Date(alert.created_at).toLocaleString()}</span>
      </div>
      {alert.mode === "notify_stub" && (
        <p className="label">A match fired — no evidence visible to you.</p>
      )}
      {alert.mode === "full" && hasReferents && (
        <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
          {alert.referent_node_ids.map((id) => (
            <li key={id} className="value">
              {id}
            </li>
          ))}
        </ul>
      )}
      {alert.mode === "full" && !hasReferents && (
        <p className="label" style={{ color: "var(--warning)" }}>
          Evidence no longer available.
        </p>
      )}
      <Button onClick={() => onJump(alert.id)} disabled={jumping}>
        {jumping ? "Jumping…" : "Jump into investigation"}
      </Button>
    </li>
  );
}

export interface JumpResultSummaryProps {
  result: AlertJumpResult;
  onOpen: (investigationId: string) => void;
}

/** `AlertJumpResult.unreadable_count` is safe to show because of what it can never mean, not
 * merely because the number itself is small: `AlertStore.get_authorized`/`list_authorized`
 * (`services/api/alerts.py`, ADR-041) filter `WHERE owner_id = $1` — an alert is only ever
 * reachable by its own recipient — and `fetch_jumpable_referents` (`watch_routes.py`) re-checks
 * every referent fresh as *this* viewer's own current principal, never a cached or historical one.
 * So `unreadable_count` can only ever recount referents belonging to an alert this same viewer
 * already had a standing claim to receive; it can shrink what they can now see, it can never
 * reveal the existence of something they had no prior claim to. The copy below is written to that
 * guarantee — "no longer accessible", never "found" or "new" — so the render layer doesn't
 * misrepresent a number the server already made safe. */
export function JumpResultSummary({ result, onOpen }: JumpResultSummaryProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
      <p className="value" data-testid="jump-seeded-summary">
        {result.seeded_count} entit{result.seeded_count === 1 ? "y" : "ies"} added to the new
        investigation.
      </p>
      {result.unreadable_count > 0 && (
        <p className="label" data-testid="jump-unreadable-summary">
          {result.unreadable_count} referent{result.unreadable_count === 1 ? "" : "s"} no longer
          accessible to you.
        </p>
      )}
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
