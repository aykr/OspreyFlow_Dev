// 4 Runs (ADR-140 decision 16, brief §7): when the dataset's pipelines run and what happened. The
// grid is one row per deployed pipeline and one cell per day, read from the run ledger (ADR-110
// decision 6); a cell opens that day's run reports. A deployed pipeline's own runs, its *Run now*,
// its schedule and its folder watch are the Publish screen's operate half, moved here (ADR-140
// decision 14: Deploy neither runs nor schedules). Held rows are the Monitoring tab's panel, reached
// here with the same rights. *Revert this load* is the operator's command, never a button: a revert
// runs with the Conduit quiesced (ADR-127 Amendment 9; ADR-140 Amendment 2, the owner's ruling).
import { useState } from "react";

import { ExpertDisclosure, disclosuresOf } from "../dag/ExpertStepDrawer";
import type { ScheduleRunView, StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { runInWords, triggerInWords } from "../../admin/Schedules";
import { HeldRowsPanel } from "../../alerts/HeldRowsPanel";
import { Button } from "../../design/primitives/Button";
import { Select } from "../../design/primitives/Select";
import type { AccessLevel } from "../../investigation/cases";
import { PublishScreen } from "../publish/PublishScreen";
import { isDeployed } from "../studio/useStudioData";
import { statusWords } from "../studio/vocabulary";
import { type DayCell, type DayState, STATE_WORDS, lastDays, rowCells } from "./runsGrid";

/** How many days the grid shows, today last (the prototype's nine). */
export const GRID_DAYS = 9;

const CELL_COLOUR: Record<DayState, string> = {
  succeeded: "var(--success)",
  attention: "var(--warning)",
  running: "var(--brass)",
  scheduled: "var(--border)",
  other: "var(--border-subtle)",
  none: "transparent",
};

const FILLED = new Set<DayState>(["succeeded", "attention", "running"]);

const CELL_MARK: Record<DayState, string> = {
  succeeded: "✓",
  attention: "!",
  running: "…",
  scheduled: "○",
  other: "–",
  none: "",
};

/** The revert, as the operator runs it (DEMO_GUIDE.md §8b; `scripts/seed_internal.py`). The name
 * after `seed_internal` only has to be a demo pack this checkout knows; the revert reads the load's
 * own record, whichever it is. */
export function revertCommand(datasetId: string | null, loadId: string, username: string | null): string {
  const pack = datasetId?.startsWith("prison-intelligence") ? "prison-intelligence" : "ledger";
  return `python -m scripts.seed_internal ${pack} --revert-load ${loadId} --reverted-by ${username || "<your username>"} --stop-api`;
}

export interface RunsTabProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  datasetId: string | null;
  datasetName: string;
  pipelines: readonly StudioRecipeDraft[] | null;
  runs: Record<string, ScheduleRunView[]>;
  /** The person's level in the case the Studio works through: what the held-rows panel offers. */
  level: AccessLevel | null;
  /** Holds `revert_loads`: is shown the command that reverts a load. */
  canRevert: boolean;
  username: string | null;
  /** Something ran or was rescheduled: read the pipelines and runs again. */
  onChanged: () => void;
  /** The day the grid ends on; the current day when left out (tests fix it). */
  today?: Date;
}

function dayInWords(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

export function RunsTab(props: RunsTabProps) {
  const { pipelines, runs } = props;
  const deployed = (pipelines ?? []).filter(isDeployed);
  const days = lastDays(props.today ?? new Date(), GRID_DAYS);
  const [selected, setSelected] = useState<{ recipeId: string; day: string } | null>(null);
  const [chosen, setChosen] = useState<string>("");
  const [operating, setOperating] = useState<string | null>(null);
  const [showHeld, setShowHeld] = useState(false);

  const rows = deployed.map((p) => ({
    pipeline: p,
    cells: rowCells(runs[p.recipe_id] ?? [], days, !!(p.schedule_cron || p.schedule_watch) && !p.schedule_paused),
  }));
  const selectedRow = rows.find((r) => r.pipeline.recipe_id === selected?.recipeId);
  const selectedCell: DayCell | undefined = selectedRow?.cells.find((c) => c.day === selected?.day);

  return (
    <div style={{ padding: "var(--sp-16)", display: "grid", gap: "var(--sp-16)", alignContent: "start" }}>
      <header style={{ display: "flex", gap: "var(--sp-8)", alignItems: "end", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <h2 style={{ margin: 0, fontSize: "var(--fs-16)" }}>Runs for {props.datasetName}</h2>
          <p className="label" style={{ margin: 0 }}>
            One row per deployed pipeline, one cell per day. Choose a cell for that day&apos;s run reports.
          </p>
        </div>
        <label style={{ display: "grid", gap: "var(--sp-2)" }}>
          <span className="label">Pipeline to run or schedule</span>
          <Select value={chosen} onChange={(e) => setChosen(e.target.value)}>
            <option value="">Choose a pipeline</option>
            {deployed.map((p) => (
              <option key={p.recipe_id} value={p.recipe_id}>
                {`${p.label} (v${p.version})`}
              </option>
            ))}
          </Select>
        </label>
        <Button disabled={!chosen} onClick={() => setOperating(chosen)}>
          Run now or schedule
        </Button>
        {/* A watched file loads a minute after it settles (ADR-110 Amendment 4); this reads the
            ledger again to show it, without leaving the tab. */}
        <Button onClick={props.onChanged}>Read the runs again</Button>
      </header>

      {pipelines !== null && deployed.length === 0 && (
        <p className="label">No pipeline of this dataset is deployed yet. Test one on the Pipelines tab, then deploy it.</p>
      )}

      {deployed.length > 0 && (
        <section aria-label="Runs by day" style={{ overflowX: "auto" }}>
          <table className="table" style={{ minWidth: 720 }}>
            <thead>
              <tr>
                <th scope="col">Pipeline</th>
                {days.map((day) => (
                  <th scope="col" key={day}>
                    {dayInWords(day)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(({ pipeline, cells }) => (
                <tr key={pipeline.recipe_id}>
                  <th scope="row" style={{ fontWeight: "normal", textAlign: "left" }}>
                    {pipeline.label}
                    <span className="label">{` · v${pipeline.version} · ${statusWords(pipeline.status)}`}</span>
                  </th>
                  {cells.map((cell) => {
                    const isSelected = selected?.recipeId === pipeline.recipe_id && selected.day === cell.day;
                    return (
                      <td key={cell.day} style={{ padding: "var(--sp-2)" }}>
                        <button
                          type="button"
                          aria-label={`${pipeline.label}, ${dayInWords(cell.day)}: ${STATE_WORDS[cell.state]}`}
                          aria-pressed={isSelected}
                          onClick={() => {
                            setSelected({ recipeId: pipeline.recipe_id, day: cell.day });
                            setShowHeld(false);
                          }}
                          style={{
                            width: "100%",
                            minWidth: 32,
                            height: 28,
                            borderRadius: "var(--r-control, 4px)",
                            border: isSelected ? "2px solid var(--text-primary)" : "1px solid var(--border-subtle)",
                            background: CELL_COLOUR[cell.state],
                            // Ink on a filled cell is the theme's ink for its filled colours.
                            color: FILLED.has(cell.state) ? "var(--brass-ink)" : "var(--text-primary)",
                            cursor: "pointer",
                          }}
                        >
                          <span aria-hidden="true">{CELL_MARK[cell.state]}</span>
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="label" style={{ margin: 0 }}>
            ✓ succeeded · ! needs a person (rows held, or a run failed, was refused or was blocked) · ○ scheduled,
            not yet run · – skipped or missed · blank: no run
          </p>
        </section>
      )}

      {selectedRow && selectedCell && (
        <section aria-label="Run report" style={{ display: "grid", gap: "var(--sp-8)" }}>
          <h3 style={{ margin: 0, fontSize: "var(--fs-14)" }}>
            {selectedRow.pipeline.label} · {dayInWords(selectedCell.day)}
          </h3>
          {/* ADR-140 decision 16: every run report discloses the pipeline's expert steps. */}
          <ExpertDisclosure steps={disclosuresOf(selectedRow.pipeline.pipeline)} title="Expert steps in this pipeline" />
          {selectedCell.runs.length === 0 ? (
            <p className="label" style={{ margin: 0 }}>
              {selectedCell.state === "scheduled" ? "Scheduled, not yet run today." : "No run that day."}
            </p>
          ) : (
            <ul aria-label="That day's runs" style={{ margin: 0, paddingLeft: "var(--sp-16)", display: "grid", gap: "var(--sp-8)" }}>
              {selectedCell.runs.map((run) => (
                <li key={run.run_id}>
                  {`${new Date(run.started_at).toLocaleTimeString("en-GB", { timeStyle: "short" })} — ${triggerInWords(run)}, as ${run.run_as}: ${runInWords(run)}`}
                  {run.load_id && props.canRevert && (
                    <div style={{ marginTop: "var(--sp-4)" }}>
                      <span className="label">Revert this load, from OspreyFlow_Core:</span>
                      <code style={{ display: "block", overflowWrap: "anywhere" }}>
                        {revertCommand(props.datasetId, run.load_id, props.username)}
                      </code>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          {props.canRevert && selectedCell.runs.some((r) => r.load_id) && (
            <p className="label" style={{ margin: 0 }}>
              A revert is the operator&apos;s command, not a button: it runs with the Conduit stopped, so nothing
              it takes back is put back while it works.
            </p>
          )}
          {selectedCell.runs.some((r) => (r.rows_held ?? 0) > 0) && (
            <div>
              <Button onClick={() => setShowHeld((shown) => !shown)}>{showHeld ? "Hide held rows" : "Open held rows"}</Button>
            </div>
          )}
          {showHeld && (
            <HeldRowsPanel
              apiBaseUrl={props.apiBaseUrl}
              bearerToken={props.bearerToken}
              investigationId={props.investigationId}
              level={props.level}
            />
          )}
        </section>
      )}

      {operating && (
        <section aria-label="Run and schedule" style={{ borderTop: "1px solid var(--border-subtle)" }}>
          <PublishScreen
            key={operating}
            apiBaseUrl={props.apiBaseUrl}
            bearerToken={props.bearerToken}
            investigationId={props.investigationId}
            recipeId={operating}
            onBack={() => setOperating(null)}
            mode="operate"
            onRan={props.onChanged}
          />
        </section>
      )}

      {deployed.length > 0 && (
        <section aria-label="Schedules and folder watches" style={{ display: "grid", gap: "var(--sp-8)" }}>
          <h3 style={{ margin: 0, fontSize: "var(--fs-14)" }}>Schedules and folder watches</h3>
          <table className="table">
            <tbody>
              {deployed.map((p) => (
                <tr key={p.recipe_id}>
                  <th scope="row" style={{ fontWeight: "normal", textAlign: "left" }}>{p.label}</th>
                  <td>{scheduleInWords(p)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

/** A pipeline's schedule and watch in a line; the editor's own words are on its run-and-schedule
 * panel, which previews the next runs. */
export function scheduleInWords(p: StudioRecipeDraft): string {
  const parts: string[] = [];
  if (p.schedule_cron) parts.push(`schedule ${p.schedule_cron}${p.schedule_timezone ? ` (${p.schedule_timezone})` : ""}`);
  if (p.schedule_watch) parts.push(`watches for ${p.schedule_watch}`);
  if (parts.length === 0) return "run by hand";
  const said = parts.join("; ");
  return p.schedule_paused ? `${said} — paused: ${p.schedule_paused_reason ?? "by hand"}` : said;
}
