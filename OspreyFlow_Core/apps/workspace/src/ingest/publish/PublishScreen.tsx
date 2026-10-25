// Stage 5 of the Ingest Studio — `spec/09_INGEST_STUDIO.md` §6. The recipe
// is written, versioned and optionally scheduled. Every action here is
// role-gated server-side (§8): publishing and scheduling need
// `source_approver`, reopening a published recipe for a further edit needs
// `source_author`, running it needs `loader` — this screen never hides an
// action a principal lacks the role for (the same "don't hide, let the
// 403 explain" discipline `RowTemplateSaveError`'s own handling in
// `map/MapScreen.tsx` already follows), it just surfaces the resulting
// error.
import { useEffect, useState } from "react";

import type {
  LoadReportView,
  PipelineRunReportView,
  ScheduleRunView,
  StudioRecipeDraft,
} from "../../../../../packages/schemas/generated";
import { runInWords, triggerInWords } from "../../admin/Schedules";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { Panel } from "../../design/primitives/Panel";
import {
  StudioActionError,
  createNewVersion,
  fetchDraft,
  fetchRecipeRegistry,
  fetchRecipeRuns,
  publishRecipe,
  runRecipe,
  setRecipeSchedulePaused,
  updateSchedule,
} from "../api";
import { DEFAULT_TIMEZONE, ScheduleEditor } from "./ScheduleEditor";
import { choiceOf, cronOf, type ScheduleChoice } from "./scheduleChoice";

/** The run route answers one of two shapes; both carry index signatures in the generated types,
 * so `in` cannot discriminate them — a pipeline run is the one whose `branches` is a real list. */
function pipelineRunOf(report: LoadReportView | PipelineRunReportView): PipelineRunReportView | null {
  return Array.isArray((report as PipelineRunReportView).branches) ? (report as PipelineRunReportView) : null;
}

export interface PublishScreenProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** `null` when the host has no active draft from this session (a fresh
   * mount that never went through Connect) — Publish is the one stage
   * that's still useful then, since a recipe published in an earlier
   * session needs revisiting (scheduling, reopening, running) without
   * redoing Connect/Profile/Map/Verify. The registry picker below is what
   * finds it. */
  recipeId: string | null;
  /** ADR-099 Amendment 3: the Studio works within a case, so there always is one. */
  investigationId: string;
  onBack: () => void;
  /** Fired once a recipe is chosen from the registry picker, so the host
   * (`IngestStudio`) can adopt it as the active draft — the same draft
   * Map/Verify would then also act on if the analyst switches tabs. */
  onSelectRecipe?: (draft: StudioRecipeDraft) => void;
  /** Fired after `createNewVersion` succeeds, so the host can hand the
   * fresh draft version back to Map for further editing — reopening a
   * published recipe (§8) lands the analyst on a new `draft` row, not on
   * this screen still showing the now-superseded one. */
  onReopenedForEditing?: (draft: StudioRecipeDraft) => void;
}

function RecipeRegistryPicker({
  apiBaseUrl,
  bearerToken,
  investigationId,
  onSelect,
}: {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  onSelect: (draft: StudioRecipeDraft) => void;
}) {
  const [recipes, setRecipes] = useState<StudioRecipeDraft[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchRecipeRegistry(apiBaseUrl, bearerToken, investigationId)
      .then((r) => {
        if (!cancelled) setRecipes(r);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-16)",
        padding: "var(--sp-16)",
      }}
    >
      <h1 style={{ fontSize: "1.1em", margin: 0 }}>Publish</h1>
      <p style={{ color: "var(--text-secondary)" }}>
        Pick a recipe from your unit's registry — draft, published, flagged or superseded — to
        publish it, change its schedule, reopen it for a further edit, or run it.
      </p>
      {error && <div role="alert">{error}</div>}
      {recipes === null && !error && <p>Loading…</p>}
      {recipes && recipes.length === 0 && (
        <p style={{ color: "var(--text-secondary)" }}>
          No recipes yet — start one in Connect first.
        </p>
      )}
      {recipes && recipes.length > 0 && (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {recipes.map((r) => (
            <li key={r.recipe_id}>
              <Button onClick={() => onSelect(r)} style={{ width: "100%", textAlign: "left" }}>
                {r.label} — {r.status} (v{r.version})
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const ERROR_MESSAGES: Record<string, string> = {
  forbidden: "You don't hold the studio role this action needs.",
  studio_recipe_not_verified:
    "This draft hasn't been verified since its last edit — go to Verify and run it again before publishing.",
  studio_recipe_not_a_draft: "This recipe has already moved past draft — nothing to publish here.",
  studio_recipe_cannot_version:
    "Only a published or flagged recipe can be reopened for a further edit.",
  recipe_not_runnable:
    "This recipe isn't published — a flagged, draft or superseded recipe can't be run.",
  source_above_clearance:
    "This source is marked above your clearance, so you can't load it. A loader cleared for its marking must run it.",
};

function friendlyError(err: unknown): string {
  if (err instanceof StudioActionError) return ERROR_MESSAGES[err.code] ?? err.message;
  return err instanceof Error ? err.message : String(err);
}

const STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  published: "Published",
  flagged: "Flagged — ontology changed since publish",
  superseded: "Superseded",
};

export function PublishScreen({
  apiBaseUrl,
  bearerToken,
  recipeId: recipeIdOrNull,
  investigationId,
  onBack,
  onSelectRecipe,
  onReopenedForEditing,
}: PublishScreenProps) {
  const [draft, setDraft] = useState<StudioRecipeDraft | null>(null);
  // ADR-110 decision 7: the schedule as a structured choice in a named zone.
  const [choice, setChoice] = useState<ScheduleChoice>({ kind: "none" });
  const [timezone, setTimezone] = useState(DEFAULT_TIMEZONE);
  const [scheduleWatch, setScheduleWatch] = useState("");
  const [runs, setRuns] = useState<ScheduleRunView[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadReport, setLoadReport] = useState<LoadReportView | PipelineRunReportView | null>(null);
  const [runSourceLocation, setRunSourceLocation] = useState("");

  useEffect(() => {
    if (!recipeIdOrNull) return;
    let cancelled = false;
    void fetchDraft(apiBaseUrl, bearerToken, investigationId, recipeIdOrNull).then((d) => {
      if (cancelled) return;
      setDraft(d);
      setChoice(choiceOf(d.schedule_cron));
      setTimezone(d.schedule_timezone ?? DEFAULT_TIMEZONE);
      setScheduleWatch(d.schedule_watch ?? "");
    });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, recipeIdOrNull, investigationId]);

  // ADR-110 decisions 6 and 7: the recipe's runs beneath its schedule, once it is published.
  const published = draft?.status === "published" || draft?.status === "flagged";
  useEffect(() => {
    if (!recipeIdOrNull || !published) return;
    let cancelled = false;
    fetchRecipeRuns(apiBaseUrl, bearerToken, investigationId, recipeIdOrNull)
      .then((r) => !cancelled && setRuns(r))
      .catch(() => !cancelled && setRuns(null));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, recipeIdOrNull, investigationId, published, loadReport]);

  if (!recipeIdOrNull) {
    return (
      <RecipeRegistryPicker
        investigationId={investigationId}
        apiBaseUrl={apiBaseUrl}
        bearerToken={bearerToken}
        onSelect={(selected) => {
          setDraft(selected);
          setChoice(choiceOf(selected.schedule_cron));
          setTimezone(selected.schedule_timezone ?? DEFAULT_TIMEZONE);
          setScheduleWatch(selected.schedule_watch ?? "");
          onSelectRecipe?.(selected);
        }}
      />
    );
  }

  const recipeId = recipeIdOrNull;

  async function refresh() {
    const fresh = await fetchDraft(apiBaseUrl, bearerToken, investigationId, recipeId);
    setDraft(fresh);
    setChoice(choiceOf(fresh.schedule_cron));
    setTimezone(fresh.schedule_timezone ?? DEFAULT_TIMEZONE);
    setScheduleWatch(fresh.schedule_watch ?? "");
    return fresh;
  }

  async function handlePublish() {
    setBusy(true);
    setError(null);
    try {
      await publishRecipe(apiBaseUrl, bearerToken, investigationId, recipeId, {
        schedule_cron: cronOf(choice),
        schedule_watch: scheduleWatch || null,
        schedule_timezone: cronOf(choice) ? timezone : null,
      });
      await refresh();
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdateSchedule() {
    setBusy(true);
    setError(null);
    try {
      await updateSchedule(apiBaseUrl, bearerToken, investigationId, recipeId, {
        schedule_cron: cronOf(choice),
        schedule_watch: scheduleWatch || null,
        schedule_timezone: cronOf(choice) ? timezone : null,
      });
      await refresh();
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handlePause(paused: boolean) {
    setBusy(true);
    setError(null);
    try {
      setDraft(await setRecipeSchedulePaused(apiBaseUrl, bearerToken, investigationId, recipeId, paused));
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleReopen() {
    setBusy(true);
    setError(null);
    try {
      const reopened = await createNewVersion(apiBaseUrl, bearerToken, investigationId, recipeId);
      setDraft(reopened);
      onReopenedForEditing?.(reopened);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRun() {
    if (!investigationId) return;
    setBusy(true);
    setError(null);
    setLoadReport(null);
    try {
      const report = await runRecipe(
        apiBaseUrl,
        bearerToken,
        investigationId,
        recipeId,
        runSourceLocation || undefined,
      );
      setLoadReport(report);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  const status = draft?.status ?? "draft";
  const canEditSchedule = status === "published" || status === "flagged";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-16)",
        padding: "var(--sp-16)",
        height: "100%",
        overflow: "auto",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
        <Button onClick={onBack}>← Back</Button>
        <h1 style={{ fontSize: "1.1em", margin: 0 }}>Publish{draft ? ` — ${draft.label}` : ""}</h1>
        <div style={{ flex: 1 }} />
        <span
          style={{
            padding: "var(--sp-4) var(--sp-8)",
            borderRadius: "var(--r-panel)",
            background: status === "flagged" ? "var(--warning-surface, var(--surface-raised))" : "var(--surface-raised)",
            border: "1px solid var(--border-strong)",
            fontSize: "0.85em",
          }}
        >
          {STATUS_LABEL[status] ?? status}
        </span>
      </div>

      {error && (
        <div
          role="alert"
          style={{
            background: "var(--surface-raised)",
            border: "1px solid var(--border-strong)",
            borderRadius: "var(--r-panel)",
            padding: "var(--sp-8)",
          }}
        >
          {error}
        </div>
      )}

      {draft?.status === "flagged" && (
        <div
          role="status"
          style={{
            background: "var(--surface-raised)",
            border: "1px solid var(--warning)",
            borderRadius: "var(--r-panel)",
            padding: "var(--sp-8)",
          }}
        >
          The ontology has changed since this recipe was published (it targets version{" "}
          {draft.ontology_version}). Its scheduled runs are blocked until someone reopens it,
          checks the mapping still holds, and republishes.
        </div>
      )}

      <Panel title="Schedule">
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)", maxWidth: 480 }}>
          <ScheduleEditor
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            choice={choice}
            timezone={timezone}
            disabled={status === "draft" ? false : !canEditSchedule}
            onChange={(next, zone) => {
              setChoice(next);
              setTimezone(zone);
            }}
          />
          {draft?.schedule_paused && (
            <p role="status" style={{ margin: 0 }}>{`Paused — ${draft.schedule_paused_reason ?? "by hand"}.`}</p>
          )}
          {draft?.schedule_owner && (
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85em", margin: 0 }}>
              {`Scheduled runs act as ${draft.schedule_owner}, who set this schedule, in the case it was set in.`}
            </p>
          )}
          {/* ADR-110 decision 5, Amendment 4: the recipe's own dataset folder, watched for a pattern. */}
          <label>
            Run when a file arrives — filename pattern
            <Input
              value={scheduleWatch}
              placeholder="*.csv"
              onChange={(e) => setScheduleWatch(e.target.value)}
              disabled={!draft?.dataset_id || (status === "draft" ? false : !canEditSchedule)}
            />
          </label>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85em", margin: 0 }}>
            {draft?.dataset_id
              ? `Each new file whose name matches, in the ${draft.dataset_id} folder, runs once, a minute after it stops changing. Leave it blank to watch nothing.`
              : "This recipe belongs to no dataset, so it has no folder to watch."}
          </p>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85em" }}>
            A recipe may be published unscheduled and run only on demand.
          </p>
        </div>
      </Panel>

      {runs && (
        <Panel title="Runs">
          {runs.length === 0 ? (
            <p style={{ margin: 0, color: "var(--text-secondary)" }}>It has not run yet.</p>
          ) : (
            <ul aria-label="Runs of this recipe" style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
              {runs.slice(0, 20).map((run) => (
                <li key={run.run_id}>
                  {`${new Date(run.slot ?? run.started_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })} — ${
                    run.trigger === "schedule" ? "" : `${triggerInWords(run)}: `
                  }${runInWords(run)}`}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      {status === "published" && (
        <Panel title="Run">
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)", maxWidth: 480 }}>
            <label>
              Source file (optional — leave blank to repeat against the recorded location)
              <Input
                value={runSourceLocation}
                onChange={(e) => setRunSourceLocation(e.target.value)}
                placeholder={draft?.source_location ?? "s3://ingest/carrier-a/2026-09.csv"}
              />
            </label>
          </div>
        </Panel>
      )}

      <div style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
        {status === "draft" && (
          <Button onClick={() => void handlePublish()} variant="primary" disabled={busy}>
            {busy ? "Publishing…" : "Publish"}
          </Button>
        )}
        {canEditSchedule && (
          <Button onClick={() => void handleUpdateSchedule()} disabled={busy}>
            {busy ? "Saving…" : "Update schedule"}
          </Button>
        )}
        {canEditSchedule && (draft?.schedule_cron || draft?.schedule_watch) && (
          <Button onClick={() => void handlePause(!draft.schedule_paused)} disabled={busy}>
            {draft.schedule_paused ? "Resume schedule" : "Pause schedule"}
          </Button>
        )}
        {(status === "published" || status === "flagged") && (
          <Button onClick={() => void handleReopen()} disabled={busy}>
            {busy ? "Reopening…" : "Reopen for editing"}
          </Button>
        )}
        {status === "published" && (
          <Button
            onClick={() => void handleRun()}
            disabled={busy || !investigationId}
            title={investigationId ? undefined : "No investigation to attribute this load to yet"}
          >
            {busy ? "Running…" : "Run now"}
          </Button>
        )}
      </div>

      {draft?.git_path && (
        <p style={{ color: "var(--text-secondary)", fontSize: "0.85em" }}>
          Committed at <code>{draft.git_path}</code>
          {draft.published_by ? ` by ${draft.published_by_name ?? draft.published_by}` : ""}
          {draft.published_at ? ` on ${new Date(draft.published_at).toLocaleString()}` : ""}.
        </p>
      )}

      {loadReport && (
        <Panel title="Load result">
          <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
            <li>Load id: {loadReport.load_id}</li>
            <li>Rows read: {loadReport.rows_read}</li>
            {!pipelineRunOf(loadReport) && (
              <li>Rows deduplicated: {(loadReport as LoadReportView).rows_deduplicated}</li>
            )}
            <li>Nodes created: {loadReport.nodes_created}</li>
            <li>Nodes referenced: {loadReport.nodes_referenced}</li>
            <li>Edges created: {loadReport.edges_created}</li>
            <li>Rows rejected: {(loadReport.rejections ?? []).length}</li>
            {(loadReport.rows_held ?? 0) > 0 && (
              <li>
                Rows held for review: {loadReport.rows_held} — a reviewer releases or rejects them in Alerts › Held rows
              </li>
            )}
          </ul>
          {/* ADR-109 ruling 1: what the case's rules did to this load, in words — a held load must
              never read as a load that simply made nothing (rule 2). */}
          {(loadReport.rule_notes ?? []).length > 0 && (
            <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }} aria-label="What the case's rules did">
              {(loadReport.rule_notes ?? []).map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
          )}
          {/* ADR-108 phase C: a pipeline run answers per branch and per stage, refusals in words —
              a stage that could not run says so here, never a silently thinner total. */}
          {pipelineRunOf(loadReport) && (
            <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }} aria-label="Pipeline stages">
              {(pipelineRunOf(loadReport)!.branches ?? []).map((branch) => (
                <li key={branch.source_id}>
                  Source “{branch.source_label}”: {branch.report.rows_read} rows read,{" "}
                  {branch.report.nodes_created} nodes created (load {branch.report.load_id})
                </li>
              ))}
              {(pipelineRunOf(loadReport)!.extracts ?? []).map((stage) => (
                <li key={stage.node_id}>
                  Extract ({stage.library}): {stage.documents_read} documents read,{" "}
                  {stage.output === "review_queue"
                    ? `${stage.candidates_queued} findings queued for review`
                    : `${stage.nodes_written_inferred} inferred entities written`}
                  {(stage.handling_overridden ?? 0) > 0
                    ? `; ${stage.handling_overridden} carry an overridden marking — ${stage.override_reason}`
                    : ""}
                  {(stage.refusals ?? []).length > 0 ? ` — refused: ${(stage.refusals ?? []).join("; ")}` : ""}
                </li>
              ))}
              {(pipelineRunOf(loadReport)!.enriches ?? []).map((stage) => (
                <li key={stage.node_id}>
                  Enrich ({stage.geocoder}): {stage.locations_considered} places considered,{" "}
                  {stage.matched_local} matched locally, {stage.matched_online} online, {stage.unmatched} unmatched
                  {(stage.refusals ?? []).length > 0 ? ` — refused: ${(stage.refusals ?? []).join("; ")}` : ""}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}
    </div>
  );
}
