// The Data feeds tab of the Reports view (`06_DECISIONS.md` ADR-110 decision 9): each pipeline
// feeding the case's datasets — its schedule in words, next run and last outcome — so a reader sees
// how fresh the case's data is. Read-only. A run's counts appear only where the Conduit sent them; where
// it withheld them (the source is above the reader's clearance, rule 3) that is said instead.
import { useEffect, useState } from "react";

import type { DataFeed } from "../../../../packages/schemas/generated";
import { runInWords } from "../admin/Schedules";
import type { ReportsApi } from "./api";
import { refusal, send } from "./caseHttp";

const when = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/London" }) : "—";

export function DataFeedsTab({ api }: { api: ReportsApi }) {
  const [feeds, setFeeds] = useState<DataFeed[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void send(api, "GET", "data-feeds").then((reply) => {
      if (!live) return;
      if (reply.ok) setFeeds(reply.body as DataFeed[]);
      else setProblem(refusal(reply, "read its data feeds").message);
    });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken, api.investigationId]);

  return (
    <div style={{ padding: "var(--sp-16)", display: "grid", gap: "var(--sp-12)", alignContent: "start" }}>
      <p className="label" style={{ margin: 0 }}>
        The pipelines that load into this case&apos;s data, and when each last ran. A run&apos;s counts are shown only where
        its source is within your clearance.
      </p>
      {problem && <p role="alert">{problem}</p>}
      {feeds?.length === 0 && <p className="label" style={{ margin: 0 }}>No pipeline loads into this case&apos;s data yet.</p>}
      {feeds && feeds.length > 0 && (
        <table className="table" aria-label="Data feeds">
          <thead>
            <tr>
              <th>Pipeline</th>
              <th>Runs</th>
              <th>Next run</th>
              <th>Last run</th>
              <th>Finished</th>
            </tr>
          </thead>
          <tbody>
            {feeds.map((f) => (
              <tr key={f.recipe_id}>
                <td>
                  <span className="value">{f.label}</span>
                  {f.flagged && <div className="label">Stopped: the ontology changed since it was published</div>}
                </td>
                <td>{f.schedule ?? "Run by hand"}</td>
                <td>{f.paused ? "Paused" : when(f.next_run)}</td>
                <td>{f.last_run ? runInWords(f.last_run) : "Not run yet"}</td>
                <td>{when(f.last_run?.finished_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
