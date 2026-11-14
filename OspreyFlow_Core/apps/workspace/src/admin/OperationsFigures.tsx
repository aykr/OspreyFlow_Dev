// Admin › Running › Operations, the deployment's view of the run ledger (`06_DECISIONS.md` ADR-141
// decisions 3, 4, 6, 7 and 14; ADR-145 decision 9): the window's runs by pipeline, unit and trigger
// per day, the scheduler's health, the external triggers with the service identity and the person
// each ran as, and the run quotas. Built by the studio lane in admin's section, by agreement (L1.7).
// A count the reader may not see is *withheld*, never a number (rule 3); no account id is shown.
import { useCallback, useEffect, useState } from "react";

import type {
  OperationsRollup,
  RunQuota,
} from "../../../../packages/schemas/generated";

type QuotaScope = RunQuota["scope"];
import { Button, Input, Select } from "../design/primitives";
import type { AdminApi } from "./api";

export const OPERATIONS_WORDS = {
  withheld: "withheld",
  withheldNote:
    "A count is withheld where one of the day's runs wrote a marking you may not view; its outcome and time are shown.",
  noRuns: "No run started in this window.",
  noExternal: "No orchestrator triggered a run in this window.",
  noQuota: "No quota is set, so no run is refused for its number.",
  quotaRight:
    "Setting a quota needs Administer system: it binds every unit's runs into a dataset.",
} as const;

const TRIGGER_WORDS: Record<string, string> = {
  manual: "Run now",
  schedule: "Schedule",
  watch: "Folder watch",
  release: "Release",
  source_refresh: "Source refresh",
  external: "External",
};

export async function operationsRuns(
  api: AdminApi,
  days: number,
): Promise<OperationsRollup> {
  const response = await fetch(
    `${api.apiBaseUrl}/v1/admin/operations/runs?days=${days}`,
    {
      headers: { Authorization: `Bearer ${api.bearerToken}` },
    },
  );
  if (!response.ok)
    throw new Error(`Operations could not be read (${response.status}).`);
  return (await response.json()) as OperationsRollup;
}

export async function setRunQuota(
  api: AdminApi,
  scope: QuotaScope,
  key: string,
  runsPerDay: number | null,
): Promise<RunQuota> {
  const response = await fetch(
    `${api.apiBaseUrl}/v1/admin/operations/quotas/${scope}/${encodeURIComponent(key)}`,
    {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${api.bearerToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ runs_per_day: runsPerDay }),
    },
  );
  if (response.status === 403) throw new Error(OPERATIONS_WORDS.quotaRight);
  if (!response.ok)
    throw new Error(`The quota was not saved (${response.status}).`);
  return (await response.json()) as RunQuota;
}

const count = (n: number | null | undefined, withheld: boolean) =>
  withheld
    ? OPERATIONS_WORDS.withheld
    : n === null || n === undefined
      ? "not measured"
      : n.toLocaleString("en-GB");

const seconds = (ms: number | null | undefined) =>
  ms === null || ms === undefined ? "—" : `${(ms / 1000).toFixed(1)} s`;

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/London",
  });

function Quotas({
  api,
  quotas,
  onSaved,
}: {
  api: AdminApi;
  quotas: RunQuota[];
  onSaved: () => void;
}) {
  const [scope, setScope] = useState<QuotaScope>("dataset");
  const [key, setKey] = useState("");
  const [limit, setLimit] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);

  const save = () => {
    setProblem(null);
    setSaid(null);
    const n = limit.trim() === "" ? null : Number(limit);
    if (!key.trim())
      return setProblem("Name the dataset or the unit the quota is for.");
    if (n !== null && (!Number.isInteger(n) || n < 1))
      return setProblem(
        "Runs a day is a whole number from 1, or empty for no limit.",
      );
    setRunQuota(api, scope, key.trim(), n)
      .then((q) => {
        setSaid(
          q.runs_per_day
            ? `${key.trim()} may now start ${q.runs_per_day} runs a day.`
            : `${key.trim()} has no limit now.`,
        );
        onSaved();
      })
      .catch((e: Error) => setProblem(e.message));
  };

  return (
    <section
      aria-label="Run quotas"
      style={{ display: "grid", gap: "var(--sp-8)" }}
    >
      <h3 style={{ margin: 0 }}>Run quotas</h3>
      {quotas.length === 0 ? (
        <p className="label" style={{ margin: 0 }}>
          {OPERATIONS_WORDS.noQuota}
        </p>
      ) : (
        <table className="table" aria-label="Run quotas">
          <thead>
            <tr>
              <th scope="col">For</th>
              <th scope="col">Runs a day</th>
              <th scope="col">Alert at</th>
            </tr>
          </thead>
          <tbody>
            {quotas.map((q) => (
              <tr key={`${q.scope}:${q.key}`}>
                <td>{`${q.scope === "dataset" ? "Dataset" : "Unit"} ${q.key}`}</td>
                <td>{q.runs_per_day ?? "no limit"}</td>
                <td>{`${Math.round((q.alert_at_share ?? 0.8) * 100)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div
        style={{
          display: "flex",
          gap: "var(--sp-8)",
          alignItems: "end",
          flexWrap: "wrap",
        }}
      >
        <label style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span>Quota for</span>
          <Select
            value={scope}
            onChange={(e) => setScope(e.target.value as QuotaScope)}
          >
            <option value="dataset">a dataset</option>
            <option value="unit">a unit</option>
          </Select>
        </label>
        <label style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span>{scope === "dataset" ? "Dataset id" : "Unit"}</span>
          <Input value={key} onChange={(e) => setKey(e.target.value)} />
        </label>
        <label style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span>Runs a day</span>
          <Input
            type="number"
            min={1}
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </label>
        <Button aria-label="Save the run quota" onClick={save}>
          Save
        </Button>
      </div>
      <p className="caption" style={{ margin: 0 }}>
        {OPERATIONS_WORDS.quotaRight}
      </p>
      {problem && <p role="alert">{problem}</p>}
      {said && <p role="status">{said}</p>}
    </section>
  );
}

export function OperationsFigures({ api }: { api: AdminApi }) {
  const [days, setDays] = useState(7);
  const [rollup, setRollup] = useState<OperationsRollup | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const read = useCallback(() => {
    operationsRuns(api, days)
      .then((r) => {
        setRollup(r);
        setProblem(null);
      })
      .catch((e: Error) => setProblem(e.message));
  }, [api, days]);
  useEffect(read, [read]);

  const rows = rollup?.rows ?? [];
  const health = rollup?.scheduler;
  const external = rollup?.external ?? [];
  return (
    <section
      aria-label="Runs and what they cost"
      style={{ display: "grid", gap: "var(--sp-12)" }}
    >
      <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "end" }}>
        <h2 style={{ margin: 0, flex: 1 }}>Runs and what they cost</h2>
        <label style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span>Window</span>
          <Select
            value={String(days)}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value="1">today</option>
            <option value="7">the last 7 days</option>
            <option value="30">the last 30 days</option>
          </Select>
        </label>
      </div>
      {problem && <p role="alert">{problem}</p>}
      {rollup && (
        <p className="caption" style={{ margin: 0 }}>
          {`Units read: ${(rollup.units ?? []).join(", ") || "none"}. ${OPERATIONS_WORDS.withheldNote}`}
        </p>
      )}
      {rollup && rows.length === 0 && (
        <p className="label" style={{ margin: 0 }}>
          {OPERATIONS_WORDS.noRuns}
        </p>
      )}
      {rows.length > 0 && (
        <table className="table" aria-label="Runs by day, pipeline and trigger">
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Pipeline</th>
              <th scope="col">Unit</th>
              <th scope="col">Trigger</th>
              <th scope="col">Runs</th>
              <th scope="col">Succeeded, refused, failed</th>
              <th scope="col">Time</th>
              <th scope="col">Rows read</th>
              <th scope="col">Graph writes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.day}:${r.pipeline_id}:${r.trigger}`}>
                <td>{r.day}</td>
                <td>{r.pipeline_label}</td>
                <td>{r.unit}</td>
                <td>{TRIGGER_WORDS[r.trigger] ?? r.trigger}</td>
                <td>{r.runs}</td>
                <td>{`${r.succeeded}, ${r.refused}, ${r.failed}`}</td>
                <td>{seconds(r.wall_ms)}</td>
                <td>{count(r.rows_read, r.withheld ?? false)}</td>
                <td>{count(r.graph_writes, r.withheld ?? false)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {health && (
        <section
          aria-label="The scheduler's health"
          style={{ display: "grid", gap: "var(--sp-4)" }}
        >
          <h3 style={{ margin: 0 }}>The scheduler's health</h3>
          <p style={{ margin: 0 }}>
            {`${health.running_now} running now; ${health.skipped} skipped while the previous run was going; ${health.missed} missed after downtime.`}
          </p>
          {(health.refused ?? []).length > 0 && (
            <ul aria-label="Refused, by reason" style={{ margin: 0 }}>
              {(health.refused ?? []).map((r) => (
                <li key={r.reason}>{`${r.count} refused: ${r.reason}`}</li>
              ))}
            </ul>
          )}
          {(health.paused ?? []).map((p) => (
            <p key={p.pipeline_id} style={{ margin: 0 }}>
              {`${p.pipeline_label} is paused${p.reason ? `: ${p.reason}` : "."}`}
            </p>
          ))}
        </section>
      )}
      {rollup && (
        <section
          aria-label="External triggers"
          style={{ display: "grid", gap: "var(--sp-4)" }}
        >
          <h3 style={{ margin: 0 }}>External triggers</h3>
          {external.length === 0 ? (
            <p className="label" style={{ margin: 0 }}>
              {OPERATIONS_WORDS.noExternal}
            </p>
          ) : (
            <table className="table" aria-label="External triggers">
              <thead>
                <tr>
                  <th scope="col">Started</th>
                  <th scope="col">Pipeline</th>
                  <th scope="col">Service identity</th>
                  <th scope="col">Ran as</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Time</th>
                </tr>
              </thead>
              <tbody>
                {external.map((t) => (
                  <tr key={t.run_id}>
                    <td>{when(t.started_at)}</td>
                    <td>{t.pipeline_label}</td>
                    <td>{t.service_identity}</td>
                    <td>{t.ran_as_name}</td>
                    <td>{t.outcome}</td>
                    <td>{seconds(t.wall_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
      {rollup && (rollup.alerts ?? []).length > 0 && (
        <section
          aria-label="Budget alerts"
          style={{ display: "grid", gap: "var(--sp-4)" }}
        >
          <h3 style={{ margin: 0 }}>Budget alerts</h3>
          <ul style={{ margin: 0 }}>
            {(rollup.alerts ?? []).map((a) => (
              <li
                key={`${a.day}:${a.scope}:${a.key}`}
              >{`${a.day}: ${a.words}.`}</li>
            ))}
          </ul>
        </section>
      )}
      {rollup && (
        <Quotas api={api} quotas={rollup.quotas ?? []} onSaved={read} />
      )}
    </section>
  );
}
