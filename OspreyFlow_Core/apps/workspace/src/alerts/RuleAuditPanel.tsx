// The rule audit (`06_DECISIONS.md` ADR-109 ruling 1): every deploy and retire, every evaluation,
// firing and failure, every hold, release and rejection — newest first, a page at a time, the
// total said. Read by the case's Authors and the unit's administrator; an entry naming something
// the reader cannot see is withheld by the server, from the page and the total alike.
import { useCallback, useEffect, useState } from "react";
import type { RuleAuditEntry } from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives";
import { readRuleAudit, type AlertsApi } from "./api";
import { when } from "./names";

const PAGE = 50;

const ACTION_WORDS: Record<string, string> = {
  rule_deployed: "Rule deployed",
  rule_retired: "Rule retired",
  rule_evaluated: "Rule ran",
  rule_fired: "Rule raised an alert",
  rule_failed: "Rule could not run",
  rows_held: "Rows held",
  rows_released: "Held rows released",
  rows_rejected: "Held rows rejected",
  alert_node_withheld: "Alert node withheld",
};

export function describeEntry(entry: RuleAuditEntry): string {
  const d = entry.detail as Record<string, unknown>;
  const parts: string[] = [];
  if (typeof d.words === "string") parts.push(d.words);
  if (typeof d.reason === "string" && d.reason) parts.push(`because ${d.reason}`);
  if (typeof d.findings === "number") parts.push(`${d.findings} finding(s)`);
  if (typeof d.trigger === "string") parts.push(d.trigger === "pre_commit" ? "before commit" : "after commit");
  if (Array.isArray(d.rows)) parts.push(`${d.rows.length} row(s)`);
  return parts.join(" · ");
}

export function RuleAuditPanel(props: AlertsApi) {
  const { apiBaseUrl, bearerToken, investigationId } = props;
  const [entries, setEntries] = useState<RuleAuditEntry[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const read = useCallback(
    (offset: number) => {
      readRuleAudit({ apiBaseUrl, bearerToken, investigationId }, offset, PAGE)
        .then((page) => {
          const got = page.entries ?? [];
          setEntries((was) => (offset === 0 ? got : [...was, ...got]));
          setTotal(page.total);
        })
        .catch((e: Error) => setProblem(e.message));
    },
    [apiBaseUrl, bearerToken, investigationId],
  );
  useEffect(() => read(0), [read]);

  if (problem) return <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>;
  if (total === null) return <p className="label">Reading…</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
      <p className="label">
        Showing {entries.length} of {total} entr{total === 1 ? "y" : "ies"}.
      </p>
      <table className="table" aria-label="Rule audit">
        <thead>
          <tr>
            <th>When</th>
            <th>Who</th>
            <th>What</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, i) => (
            <tr key={`${entry.recorded_at}-${i}`}>
              <td>{when(entry.recorded_at)}</td>
              <td>{entry.principal_id}</td>
              <td>{ACTION_WORDS[entry.action] ?? entry.action}</td>
              <td>{describeEntry(entry)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {entries.length < total && <Button onClick={() => read(entries.length)}>Show more</Button>}
    </div>
  );
}
