import { useEffect, useState } from "react";

import { LinkChangeError, fetchLinkHistory, type LinkHistory as History } from "./linkChangeApi";
import { describeChange } from "./describeChange";

export interface LinkHistoryProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The selected link's id. A change gives a link a new id, so the history reloads with it. */
  edgeId: string;
}

type Load =
  | { state: "loading" }
  | { state: "ready"; history: History }
  | { state: "refused"; message: string };

function when(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

/** The Inspector's **History** section for a selected link (ADR-080): every change that led to it,
 * newest first — who, when, why, and what moved from what to what. A link nobody has changed says
 * so. Read only; the record is kept by the server and cannot be edited from here. */
export function LinkHistory({ apiBaseUrl, bearerToken, investigationId, edgeId }: LinkHistoryProps) {
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    let current = true;
    setLoad({ state: "loading" });
    fetchLinkHistory(apiBaseUrl, bearerToken, investigationId, edgeId).then(
      (history) => {
        if (current) setLoad({ state: "ready", history });
      },
      (error: unknown) => {
        if (!current) return;
        setLoad({
          state: "refused",
          message:
            error instanceof LinkChangeError && error.kind === "link_not_found"
              ? "This link is not in your view, so its history cannot be shown."
              : "The history could not be loaded. Select the link again to retry.",
        });
      },
    );
    return () => {
      current = false;
    };
  }, [apiBaseUrl, bearerToken, investigationId, edgeId]);

  return (
    <section aria-label="Change history" style={{ marginTop: "var(--sp-16)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)", color: "var(--text-secondary)" }}>
        Change history
        {load.state === "ready" && load.history.changes.length > 0
          ? ` (${load.history.changes.length})`
          : ""}
      </h3>
      {load.state === "loading" && <p style={{ color: "var(--text-tertiary)" }}>Loading history…</p>}
      {load.state === "refused" && (
        <p role="alert" style={{ color: "var(--text-secondary)" }}>
          {load.message}
        </p>
      )}
      {load.state === "ready" && load.history.changes.length === 0 && (
        <p style={{ color: "var(--text-tertiary)" }}>
          This link has not been changed since it was recorded.
        </p>
      )}
      {load.state === "ready" && load.history.changes.length > 0 && (
        <ol style={{ listStyle: "none", margin: "var(--sp-8) 0 0", padding: 0, display: "grid", gap: "var(--sp-8)" }}>
          {load.history.changes.map((change) => (
            <li
              key={change.id}
              style={{
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--r-control)",
                padding: "var(--sp-8)",
              }}
            >
              <div style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
                {change.changed_by} · {when(change.changed_at)}
              </div>
              <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{change.reason}</div>
              <ul style={{ margin: "var(--sp-4) 0 0", paddingLeft: "var(--sp-16)" }}>
                {describeChange(change).map((line) => (
                  <li key={line} className="value">
                    {line}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
      {load.state === "ready" && load.history.truncated && (
        <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
          Older changes are not shown here.
        </p>
      )}
    </section>
  );
}
