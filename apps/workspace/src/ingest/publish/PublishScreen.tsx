// Stage 5 of the Ingest Studio — `docs/09_INGEST_STUDIO.md` §6. The recipe
// is written, versioned and optionally scheduled. Every action here is
// role-gated server-side (§8): publishing and scheduling need
// `source_approver`, reopening a published recipe for a further edit needs
// `source_author`, running it needs `loader` — this screen never hides an
// action a principal lacks the role for (the same "don't hide, let the
// 403 explain" discipline `RowTemplateSaveError`'s own handling in
// `map/MapScreen.tsx` already follows), it just surfaces the resulting
// error.
import { useEffect, useState } from "react";

import type { LoadReport, StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { Panel } from "../../design/primitives/Panel";
import {
  StudioActionError,
  createNewVersion,
  fetchDraft,
  fetchRecipeRegistry,
  publishRecipe,
  runRecipe,
  updateSchedule,
} from "../api";

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
  investigationId: string | null;
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
  onSelect,
}: {
  apiBaseUrl: string;
  bearerToken: string;
  onSelect: (draft: StudioRecipeDraft) => void;
}) {
  const [recipes, setRecipes] = useState<StudioRecipeDraft[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchRecipeRegistry(apiBaseUrl, bearerToken)
      .then((r) => {
        if (!cancelled) setRecipes(r);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken]);

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
  const [scheduleCron, setScheduleCron] = useState("");
  const [scheduleWatch, setScheduleWatch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadReport, setLoadReport] = useState<LoadReport | null>(null);
  const [runSourceLocation, setRunSourceLocation] = useState("");

  useEffect(() => {
    if (!recipeIdOrNull) return;
    let cancelled = false;
    void fetchDraft(apiBaseUrl, bearerToken, recipeIdOrNull).then((d) => {
      if (cancelled) return;
      setDraft(d);
      setScheduleCron(d.schedule_cron ?? "");
      setScheduleWatch(d.schedule_watch ?? "");
    });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, recipeIdOrNull]);

  if (!recipeIdOrNull) {
    return (
      <RecipeRegistryPicker
        apiBaseUrl={apiBaseUrl}
        bearerToken={bearerToken}
        onSelect={(selected) => {
          setDraft(selected);
          setScheduleCron(selected.schedule_cron ?? "");
          setScheduleWatch(selected.schedule_watch ?? "");
          onSelectRecipe?.(selected);
        }}
      />
    );
  }

  const recipeId = recipeIdOrNull;

  async function refresh() {
    const fresh = await fetchDraft(apiBaseUrl, bearerToken, recipeId);
    setDraft(fresh);
    setScheduleCron(fresh.schedule_cron ?? "");
    setScheduleWatch(fresh.schedule_watch ?? "");
    return fresh;
  }

  async function handlePublish() {
    setBusy(true);
    setError(null);
    try {
      await publishRecipe(apiBaseUrl, bearerToken, recipeId, {
        schedule_cron: scheduleCron || null,
        schedule_watch: scheduleWatch || null,
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
      await updateSchedule(apiBaseUrl, bearerToken, recipeId, {
        schedule_cron: scheduleCron || null,
        schedule_watch: scheduleWatch || null,
      });
      await refresh();
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
      const reopened = await createNewVersion(apiBaseUrl, bearerToken, recipeId);
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
        <Button onClick={onBack}>← Connect</Button>
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
          <label>
            Cron
            <Input
              value={scheduleCron}
              onChange={(e) => setScheduleCron(e.target.value)}
              placeholder="0 6 * * *"
              disabled={status === "draft" ? false : !canEditSchedule}
            />
          </label>
          <label>
            Watch (object storage prefix)
            <Input
              value={scheduleWatch}
              onChange={(e) => setScheduleWatch(e.target.value)}
              placeholder="s3://ingest/carrier-a/*.csv"
              disabled={status === "draft" ? false : !canEditSchedule}
            />
          </label>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85em" }}>
            Both are optional — a recipe may be published unscheduled and run only on demand.
          </p>
        </div>
      </Panel>

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
          {draft.published_by ? ` by ${draft.published_by}` : ""}
          {draft.published_at ? ` on ${new Date(draft.published_at).toLocaleString()}` : ""}.
        </p>
      )}

      {loadReport && (
        <Panel title="Load result">
          <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
            <li>Load id: {loadReport.load_id}</li>
            <li>Rows read: {loadReport.rows_read}</li>
            <li>Rows deduplicated: {loadReport.rows_deduplicated}</li>
            <li>Nodes created: {loadReport.nodes_created}</li>
            <li>Nodes referenced: {loadReport.nodes_referenced}</li>
            <li>Edges created: {loadReport.edges_created}</li>
            <li>Rows rejected: {(loadReport.rejections ?? []).length}</li>
          </ul>
        </Panel>
      )}
    </div>
  );
}
