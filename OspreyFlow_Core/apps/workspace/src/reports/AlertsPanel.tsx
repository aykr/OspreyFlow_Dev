// The *Alerts* panel (ADR-146 decision 9): the Glass shows alerts where people already look,
// without becoming a second place to work them. Open alerts by source and age, and the newest few.
// On a case's Figures, on the Alert monitoring board, and (once L3.3 builds them) on any drawing
// board.
//
// Every count is the Conduit's, taken as the reader (rule 7): the panel adds figures up, never
// counts rows itself. The newest few are the queue's own rows, which go only to a reader the
// Conduit offers them to; anyone else is shown the counts alone. A row opens the alert at its
// address only for someone Rules and Monitoring is offered to (`onOpenAlert`); for anyone else it
// is words, since the Glass never works an alert.
import { useEffect, useState } from "react";

import type { MonitoringFigures, QueuedAlert } from "../../../../packages/schemas/generated";
import { typologyLabel } from "../alerts/names";
import { Button } from "../design/primitives";
import { fetchNewestAlerts, type ReportsApi } from "./api";
import { AGE_BANDS, groupKey, groupName, NUMBER, plural, Section, type RuleGroup } from "./figureParts";

export const NEWEST_FEW = 5;
const KIND_GROUP: Record<string, string> = { typology: "typology", hotlist: "hotlists", monitor: "monitors" };

/** The rule group a queued alert is counted under, as the Conduit's `_group` names it. */
export function groupOf(row: QueuedAlert): RuleGroup {
  const kind = row.kind ?? "typology";
  return { label: KIND_GROUP[kind] ?? kind, typology: kind === "typology" ? (row.alert.typology ?? "") : "" };
}

export interface AlertsPanelProps {
  api: ReportsApi;
  monitoring: MonitoringFigures | null;
  /** Only the rule group shown (the Alert monitoring board's filter); every group when left out. */
  only?: RuleGroup | null;
  /** Opens an alert at its address; given only when Rules and Monitoring is offered to the reader. */
  onOpenAlert?: (alertId: string) => void;
  /** Drawn outlined: the panel an alert opened this screen for (ADR-145 Amendment 4 decision 10). */
  outlined?: boolean;
  now?: Date;
}

function ageOf(createdAt: string, now: Date): string {
  const days = (now.getTime() - new Date(createdAt).getTime()) / 86_400_000;
  if (days < 1) return "today";
  const whole = Math.floor(days);
  return whole === 1 ? "1 day old" : `${whole} days old`;
}

export function AlertsPanel({ api, monitoring, only = null, onOpenAlert, outlined = false, now = new Date() }: AlertsPanelProps) {
  const [newest, setNewest] = useState<QueuedAlert[] | null | "unread">(null);
  useEffect(() => {
    let live = true;
    // Every row still in the queue, filtered to the panel's rule group before the newest few are
    // taken, so a filtered board never shows none while its counts show some.
    fetchNewestAlerts(api, Number.MAX_SAFE_INTEGER)
      .then((rows) => live && setNewest(rows))
      .catch(() => live && setNewest("unread"));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken, api.investigationId]);

  const counts = (monitoring?.open_by_source ?? []).filter((c) => !only || groupKey(c as RuleGroup) === groupKey(only));
  const groups = [...new Map(counts.map((c) => [groupKey(c as RuleGroup), c as RuleGroup])).values()];
  const total = counts.reduce((n, c) => n + c.count, 0);
  const cell = (g: RuleGroup, age: string) =>
    counts.filter((c) => groupKey(c as RuleGroup) === groupKey(g) && c.age === age).reduce((n, c) => n + c.count, 0);
  const rows = Array.isArray(newest) ? newest.filter((r) => !only || groupKey(groupOf(r)) === groupKey(only)).slice(0, NEWEST_FEW) : null;

  return (
    <Section title="Alerts" id="figures-alerts" outlined={outlined}>
      {monitoring === null ? (
        <p className="label" style={{ margin: 0 }}>Counting…</p>
      ) : (
        <>
          <p className="value" style={{ margin: 0 }}>{`${plural(total, "alert")} open`}</p>
          {groups.length > 0 && (
            <table className="table" aria-label="Open alerts by source and age">
              <thead>
                <tr>
                  <th>Source</th>
                  {AGE_BANDS.map((age) => (
                    <th key={age} style={{ textAlign: "right" }}>{age[0]!.toUpperCase() + age.slice(1)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => (
                  <tr key={groupKey(g)}>
                    <td>{groupName(g)}</td>
                    {AGE_BANDS.map((age) => (
                      <td key={age} style={{ textAlign: "right" }}>{NUMBER.format(cell(g, age))}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      {rows && rows.length > 0 && (
        <>
          <h4 className="label" style={{ margin: 0 }}>Newest</h4>
          <ul aria-label="Newest alerts" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
            {rows.map((r) => {
              const words = `${r.alert.typology ? typologyLabel(r.alert.typology) : groupName(groupOf(r))}: ${r.summary}`;
              const age = ageOf(r.alert.created_at, now);
              return (
                <li key={r.alert.id} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "baseline" }}>
                  {onOpenAlert ? (
                    <Button onClick={() => onOpenAlert(r.alert.id)}>{words}</Button>
                  ) : (
                    <span>{words}</span>
                  )}
                  <span className="label">{age}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}
      {newest === "unread" && <p className="label" style={{ margin: 0 }}>The newest alerts could not be read just now.</p>}
    </Section>
  );
}
