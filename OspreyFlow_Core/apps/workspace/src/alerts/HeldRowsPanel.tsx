// Rows a failing pre-commit rule held out of the graph (`06_DECISIONS.md` ADR-109 ruling 1, fail
// closed): what was held, by which rule, and why — and, for an Author, releasing them (they load
// then, provenance unchanged) or rejecting them with a reason. Only rows at or below the reader's
// marking are listed; the server filters them in its own query.
import { useCallback, useEffect, useState } from "react";
import type { HeldRow } from "../../../../packages/schemas/generated";
import { COUNTS_WITHHELD_REASON } from "../admin/Schedules";
import { Button } from "../design/primitives";
import { rowNumber } from "../inspector/sourceLocator";
import type { AccessLevel } from "../investigation/cases";
import { listHeldRows, rejectHeldRows, releaseHeldRows, type AlertsApi } from "./api";
import { when } from "./names";

export interface HeldRowsPanelProps extends AlertsApi {
  level: AccessLevel | null;
}

/** Held rows grouped by the load that held them: a release is one load at a time. */
function byLoad(rows: HeldRow[]): Map<string, HeldRow[]> {
  const groups = new Map<string, HeldRow[]>();
  for (const row of rows) groups.set(row.load_id, [...(groups.get(row.load_id) ?? []), row]);
  return groups;
}

export function HeldRowsPanel(props: HeldRowsPanelProps) {
  const { apiBaseUrl, bearerToken, investigationId, level } = props;
  const [rows, setRows] = useState<HeldRow[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});

  const reload = useCallback(() => {
    listHeldRows({ apiBaseUrl, bearerToken, investigationId })
      .then(setRows)
      .catch((e: Error) => setProblem(e.message));
  }, [apiBaseUrl, bearerToken, investigationId]);
  useEffect(reload, [reload]);

  if (problem && rows === null) return <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>;
  if (rows === null) return <p className="label">Reading…</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-16)" }}>
      {said && <p role="status" className="label">{said}</p>}
      {problem && <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>}
      {rows.length === 0 && <p className="label">Nothing is held for review.</p>}
      {[...byLoad(rows)].map(([loadId, group]) => {
        const reason = reasons[loadId] ?? "";
        const ids = group.map((r) => r.id);
        const first = group[0];
        if (!first) return null;
        return (
          <section key={loadId} aria-label={`Held from load ${loadId}`} style={{ border: "1px solid var(--border-subtle)", padding: "var(--sp-12)", display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
            <p className="value" style={{ margin: 0 }}>
              {group.length} row{group.length === 1 ? "" : "s"} of {first.source}, held {when(first.held_at)}
            </p>
            <p className="label" style={{ margin: 0 }}>Why: {first.reason}</p>
            <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
              {group.map((row) => (
                <li key={row.id} className="label">
                  Row {rowNumber(row.row_index)}: {Object.entries(row.row).map(([k, v]) => `${k} ${v}`).join(" · ")}
                </li>
              ))}
            </ul>
            {level === "author" && (
              <>
                <label className="label" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
                  Reason (required to reject)
                  <textarea
                    className="input"
                    rows={2}
                    aria-label={`Reason for load ${loadId}`}
                    value={reason}
                    onChange={(e) => setReasons({ ...reasons, [loadId]: e.target.value })}
                  />
                </label>
                <div style={{ display: "flex", gap: "var(--sp-8)" }}>
                  <Button
                    variant="primary"
                    onClick={() =>
                      void releaseHeldRows(props, first.recipe_id, ids, reason.trim() || null)
                        .then((report) => {
                          setSaid(
                            report.withheld
                              ? `Released and loaded. Counts withheld — ${COUNTS_WITHHELD_REASON}.`
                              : `Released and loaded: ${report.edges_created} link(s) made. ${report.rule_notes.join(" ")}`.trim(),
                          );
                          reload();
                        })
                        .catch((e: Error) => setProblem(e.message))
                    }
                  >
                    Release and load
                  </Button>
                  <Button
                    disabled={!reason.trim()}
                    onClick={() =>
                      void rejectHeldRows(props, ids, reason.trim())
                        .then(() => {
                          setSaid(`Rejected ${ids.length} row(s); they will not be loaded.`);
                          reload();
                        })
                        .catch((e: Error) => setProblem(e.message))
                    }
                  >
                    Reject
                  </Button>
                </div>
              </>
            )}
          </section>
        );
      })}
    </div>
  );
}
