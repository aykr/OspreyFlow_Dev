// *What raises alerts* (`06_DECISIONS.md` ADR-146 decision 5): every rule and watch in one list —
// name and maker, source (Rule or Watch), dataset, owner, draft or live, expiry, when it last fired,
// alerts in the last 30 days and the share closed as not of interest — with a filter on each
// column, and beside each rule or watch the alerts of it suppressed today (Amendment 1). Every
// count is the reader's own queue's, taken by the Conduit (rule 7): the Glass counts nothing.
import { useEffect, useMemo, useState } from "react";
import type { AlertSource } from "../../../../packages/schemas/generated";
import { Input } from "../design/primitives";
import { listAlertSources, type AlertsApi } from "./api";
import { when } from "./names";

const STATE_WORDS: Record<string, string> = { live: "Live", draft: "Draft", stopped: "Stopped" };

function share(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

/** The words a column is filtered on, one per column, as shown. */
function cells(s: AlertSource): Record<string, string> {
  return {
    name: s.name,
    maker: s.maker_name ?? s.maker,
    source: s.source === "rule" ? "Rule" : "Watch",
    dataset: s.dataset_id ?? "—",
    owner: s.owner,
    state: STATE_WORDS[s.state] ?? s.state,
  };
}

const COLUMNS: { key: keyof ReturnType<typeof cells>; label: string }[] = [
  { key: "name", label: "Name" },
  { key: "maker", label: "Maker" },
  { key: "source", label: "Source" },
  { key: "dataset", label: "Dataset" },
  { key: "owner", label: "Owner" },
  { key: "state", label: "Draft or live" },
];

export function AlertSourcesPanel(api: AlertsApi) {
  const [sources, setSources] = useState<AlertSource[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({});
  useEffect(() => {
    let cancelled = false;
    listAlertSources(api)
      .then((r) => !cancelled && setSources(r.sources))
      .catch((e: Error) => !cancelled && setProblem(e.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken, api.investigationId]);
  const shown = useMemo(
    () =>
      (sources ?? []).filter((s) => {
        const c = cells(s);
        return COLUMNS.every(({ key }) => { const f = filters[key]; return !f || (c[key] ?? "").toLowerCase().includes(f.toLowerCase()); });
      }),
    [sources, filters],
  );
  if (problem) return <p role="alert" style={{ color: "var(--error)" }}>{problem}</p>;
  if (sources === null) return <p className="label">Reading what raises alerts…</p>;
  return (
    <section aria-label="What raises alerts" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)", overflowX: "auto" }}>
      <h3 className="value" style={{ margin: 0 }}>Every rule and watch</h3>
      <p className="label" style={{ margin: 0 }}>
        {`${shown.length} of ${sources.length} shown. Counts are of the alerts you can see.`}
      </p>
      <table className="table" aria-label="Rules and watches">
        <thead>
          <tr>
            {COLUMNS.map((c) => (
              <th key={c.key} scope="col">
                {c.label}
              </th>
            ))}
            <th scope="col">Expires</th>
            <th scope="col">Last fired</th>
            <th scope="col" style={{ textAlign: "right" }}>Alerts, 30 days</th>
            <th scope="col" style={{ textAlign: "right" }}>Not of interest</th>
          </tr>
          <tr>
            {COLUMNS.map((c) => (
              <th key={c.key}>
                <Input
                  aria-label={`Filter by ${c.label.toLowerCase()}`}
                  value={filters[c.key] ?? ""}
                  onChange={(e) => setFilters({ ...filters, [c.key]: e.target.value })}
                  placeholder="Filter"
                />
              </th>
            ))}
            <th colSpan={4} />
          </tr>
        </thead>
        <tbody>
          {shown.map((s) => {
            const c = cells(s);
            return (
              <tr key={`${s.source}-${s.id}`}>
                {COLUMNS.map(({ key }) => (
                  <td key={key}>
                    {c[key]}
                    {key === "name" &&
                      (s.suppressed ?? []).map((q) => (
                        <div key={q.alert_id} className="label" style={{ color: "var(--warning)" }}>
                          {`One alert suppressed until ${when(q.until)}: ${q.reason}`}
                        </div>
                      ))}
                  </td>
                ))}
                <td>{s.expires_on ? when(s.expires_on) : "—"}</td>
                <td>{s.last_fired_at ? when(s.last_fired_at) : "Never"}</td>
                <td style={{ textAlign: "right" }}>{s.alerts_30_days ?? 0}</td>
                <td style={{ textAlign: "right" }}>{share(s.not_of_interest)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
