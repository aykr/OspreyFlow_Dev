// The Admin area's Schedules and runs (`06_DECISIONS.md` ADR-110 decision 8, Amendment 2): every
// scheduled recipe across the deployment — its schedule in words, case, owner, next run and last
// outcome — with Pause, Resume and its run history. A run's counts appear only where the Conduit sent
// them; where it withheld them (the source is above the administrator's clearance, rule 3) that is
// said, and nothing is shown in their place.
import { useEffect, useState } from "react";

import type { AdminSchedule, ScheduleRunView } from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives";
import { DEFAULT_TIMEZONE, ScheduleEditor } from "../ingest/publish/ScheduleEditor";
import { choiceOf, cronOf, type ScheduleChoice } from "../ingest/publish/scheduleChoice";
import {
  changeSchedule,
  listSchedules,
  pauseSchedule,
  resumeSchedule,
  runScheduleNow,
  scheduleRuns,
  type AdminApi,
} from "./api";

const OUTCOME: Record<ScheduleRunView["outcome"], string> = {
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  refused: "Refused",
  blocked: "Blocked",
  skipped: "Skipped",
  missed: "Missed",
};

const when = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/London" }) : "—";

/** Why a run's counts are not shown (rule 3, ADR-127 Amendment 25; ADR-124 option A′: a withheld
 * count says that it withholds, and never shows a zero). A count of what a run loaded includes every
 * row it wrote, at each marking it wrote them at. */
export const COUNTS_WITHHELD_REASON =
  "some of what it loaded is above your clearance or restricted to another unit";

/** One run in words: its outcome, then its counts, or why there are none. */
export function runInWords(run: ScheduleRunView): string {
  const outcome = OUTCOME[run.outcome];
  if (run.withheld) return `${outcome}: counts withheld — ${COUNTS_WITHHELD_REASON}`;
  if (run.rows_read !== null && run.rows_read !== undefined) {
    return (
      `${outcome}: ${run.rows_read} rows read, ${run.nodes_created ?? 0} created, ` +
      `${run.nodes_referenced ?? 0} referenced, ${run.rows_rejected ?? 0} rejected` +
      (run.rows_held ? `, ${run.rows_held} held` : "")
    );
  }
  return run.failure ? `${outcome}: ${run.failure}` : outcome;
}

/** What started a run, for a list of runs: a watched run names its file (ADR-110 Amendment 4),
 * which the Conduit leaves out where the reader may not view the source. */
export function triggerInWords(run: ScheduleRunView): string {
  if (run.trigger === "watch") return run.file ? `watch, ${run.file}` : "watch";
  return run.trigger;
}

function History({ api, schedule }: { api: AdminApi; schedule: AdminSchedule }) {
  const [runs, setRuns] = useState<ScheduleRunView[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    scheduleRuns(api, schedule.recipe_id).then(setRuns).catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schedule.recipe_id]);
  if (problem) return <p role="alert">{problem}</p>;
  if (!runs) return <p className="label">Reading its runs…</p>;
  if (runs.length === 0) return <p className="label">It has not run yet.</p>;
  return (
    <ul aria-label={`Runs of ${schedule.label}`} style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
      {runs.map((run) => (
        <li key={run.run_id}>
          <span className="value">{when(run.slot ?? run.started_at)}</span>{" "}
          <span className="label">{`${run.trigger === "schedule" ? "" : `(${triggerInWords(run)}) `}${runInWords(run)}`}</span>
        </li>
      ))}
    </ul>
  );
}

export function Schedules({ api }: { api: AdminApi }) {
  const [schedules, setSchedules] = useState<AdminSchedule[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  // ADR-110 Amendment 3: the schedule being changed, as the Studio's structured choice.
  const [editing, setEditing] = useState<{ recipeId: string; choice: ScheduleChoice; timezone: string } | null>(null);

  useEffect(() => {
    listSchedules(api).then(setSchedules).catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);

  const replace = (changed: AdminSchedule) =>
    setSchedules((all) => (all ?? []).map((s) => (s.recipe_id === changed.recipe_id ? changed : s)));
  const act = (step: Promise<AdminSchedule>, done?: (s: AdminSchedule) => string) => {
    setProblem(null);
    setSaid(null);
    step
      .then((s) => {
        replace(s);
        if (done) setSaid(done(s));
      })
      .catch((e: Error) => setProblem(e.message));
  };
  const save = (s: AdminSchedule) => {
    const cron = editing ? cronOf(editing.choice) : null;
    if (!editing || !cron) return;
    act(changeSchedule(api, s.recipe_id, cron, editing.timezone), (changed) => {
      setEditing(null);
      return `${changed.label} now runs ${changed.schedule}, still as ${changed.owner ?? "its owner"}.`;
    });
  };

  return (
    <>
      <p className="label" style={{ margin: 0 }}>
        Every scheduled recipe in this deployment. A scheduled run acts as its owner, in the case the schedule was set
        in. A run&apos;s counts are shown only where its source is within your clearance.
      </p>
      {problem && <p role="alert">{problem}</p>}
      {said && <p role="status">{said}</p>}
      {schedules?.length === 0 && <p className="label" style={{ margin: 0 }}>No recipe is scheduled.</p>}
      {schedules && schedules.length > 0 && (
        <table className="table" aria-label="Scheduled recipes">
          <thead>
            <tr>
              <th>Recipe</th>
              <th>Case</th>
              <th>Schedule</th>
              <th>Owner</th>
              <th>Next run</th>
              <th>Last run</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {schedules.map((s) => (
              <tr key={s.recipe_id}>
                <td>
                  <span className="value">{s.label}</span>
                  {s.flagged && <div className="label">Blocked: the ontology changed since it was published</div>}
                  {s.paused && <div className="label">{s.paused_reason ?? "paused"}</div>}
                  {open === s.recipe_id && <History api={api} schedule={s} />}
                  {editing?.recipeId === s.recipe_id && (
                    <div style={{ display: "grid", gap: "var(--sp-8)", marginTop: "var(--sp-8)" }}>
                      <ScheduleEditor
                        apiBaseUrl={api.apiBaseUrl}
                        bearerToken={api.bearerToken}
                        choice={editing.choice}
                        timezone={editing.timezone}
                        onChange={(choice, timezone) => setEditing({ recipeId: s.recipe_id, choice, timezone })}
                      />
                      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
                        <Button variant="primary" aria-label={`Save schedule of ${s.label}`} onClick={() => save(s)}>
                          Save
                        </Button>
                        <Button aria-label={`Cancel changing ${s.label}`} onClick={() => setEditing(null)}>
                          Cancel
                        </Button>
                      </div>
                      <p className="label" style={{ margin: 0 }}>{`It keeps its owner, ${s.owner ?? "—"}.`}</p>
                    </div>
                  )}
                </td>
                <td>{s.case_id ?? "—"}</td>
                <td>{s.schedule}</td>
                <td>{s.owner ?? "—"}</td>
                <td>{s.paused ? "Paused" : when(s.next_run)}</td>
                <td>{s.last_run ? runInWords(s.last_run) : "Not run yet"}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {s.paused ? (
                    <Button aria-label={`Resume ${s.label}`} onClick={() => act(resumeSchedule(api, s.recipe_id))}>
                      Resume
                    </Button>
                  ) : (
                    <Button aria-label={`Pause ${s.label}`} onClick={() => act(pauseSchedule(api, s.recipe_id))}>
                      Pause
                    </Button>
                  )}{" "}
                  <Button
                    aria-label={`Run ${s.label} now`}
                    onClick={() =>
                      act(runScheduleNow(api, s.recipe_id), (ran) => `${ran.label} was run now; it runs as ${ran.owner ?? "its owner"}.`)
                    }
                  >
                    Run now
                  </Button>{" "}
                  <Button
                    aria-label={`Change schedule of ${s.label}`}
                    onClick={() =>
                      setEditing({ recipeId: s.recipe_id, choice: choiceOf(s.cron), timezone: s.timezone || DEFAULT_TIMEZONE })
                    }
                  >
                    Change
                  </Button>{" "}
                  <Button
                    aria-label={`${open === s.recipe_id ? "Hide" : "Show"} runs of ${s.label}`}
                    aria-expanded={open === s.recipe_id}
                    onClick={() => setOpen(open === s.recipe_id ? null : s.recipe_id)}
                  >
                    Runs
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
