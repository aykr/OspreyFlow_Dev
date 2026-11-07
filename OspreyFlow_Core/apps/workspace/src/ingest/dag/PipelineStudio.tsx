// The Ingest Studio's Pipelines place (ADR-108 phase B; phase 6, ADR-108 Amendment 6): a pipelines
// home, then the pipeline with a drawer beside it (`NodeDrawer`), drawn as the canvas in expert mode
// and as a numbered list in guided mode. The save gate stays the server's: a violation comes back as
// words and is shown, never swallowed.
import { useEffect, useState } from "react";

import type {
  PipelineGraph,
  PipelineNode,
  StudioRecipeDraft,
} from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { createDraft, fetchDraft, fetchRecipeRegistry, savePipeline } from "../api";
import { MapEditor } from "../map/MapEditor";
import { PublishScreen } from "../publish/PublishScreen";
import { statusWords } from "../studio/vocabulary";
import { GuidedSteps, guidedMayNotRemove } from "./GuidedSteps";
import { NodeDrawer, type DrawerPane } from "./NodeDrawer";
import { PipelineCanvas } from "./PipelineCanvas";
import { addEnrichAfter, addExtractAfter, addSourceChain, removeNode } from "./pipelineGraphEdit";
import { readStudioMode, writeStudioMode, type StudioMode } from "./studioMode";

export interface PipelineStudioProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** A pipeline was deployed or reopened: the readiness strip and the Runs tab read again. */
  onChanged?: () => void;
  /** The signed-in person, whose guided or expert mode this is (ADR-140 decision 3). */
  username?: string | null;
}

type View =
  | { at: "home" }
  | { at: "canvas"; recipeId: string; selectedId?: string | null }
  | { at: "map"; recipeId: string; pipeline: PipelineGraph; mapNodeId: string }
  // A published or flagged recipe from before pipelines has no canvas: it opens where it is
  // republished, and goes back to the home.
  | { at: "publish"; recipeId: string };

export function PipelineStudio({ apiBaseUrl, bearerToken, investigationId, onChanged, username }: PipelineStudioProps) {
  const [view, setView] = useState<View>({ at: "home" });

  if (view.at === "home") {
    return (
      <PipelinesHome
        apiBaseUrl={apiBaseUrl}
        bearerToken={bearerToken}
        investigationId={investigationId}
        onOpen={(recipe) =>
          setView(
            recipe.pipeline || recipe.status === "draft"
              ? { at: "canvas", recipeId: recipe.recipe_id }
              : { at: "publish", recipeId: recipe.recipe_id },
          )
        }
      />
    );
  }
  if (view.at === "publish") {
    return (
      <PublishScreen
        apiBaseUrl={apiBaseUrl}
        bearerToken={bearerToken}
        investigationId={investigationId}
        recipeId={view.recipeId}
        onBack={() => setView({ at: "home" })}
        onSelectRecipe={() => undefined}
        onReopenedForEditing={() => {
          onChanged?.();
          setView({ at: "canvas", recipeId: view.recipeId });
        }}
        onRan={onChanged}
      />
    );
  }
  if (view.at === "map") {
    return (
      <MapEditor
        apiBaseUrl={apiBaseUrl}
        bearerToken={bearerToken}
        investigationId={investigationId}
        recipeId={view.recipeId}
        pipeline={view.pipeline}
        mapNodeId={view.mapNodeId}
        onStep={(node) => setView({ at: "canvas", recipeId: view.recipeId, selectedId: node.id })}
      />
    );
  }
  return (
    <PipelineEditor
      key={view.recipeId}
      apiBaseUrl={apiBaseUrl}
      bearerToken={bearerToken}
      investigationId={investigationId}
      recipeId={view.recipeId}
      initialSelectedId={view.selectedId ?? null}
      username={username ?? null}
      onChanged={onChanged}
      onHome={() => setView({ at: "home" })}
      onOpenMap={(pipeline, mapNodeId) => setView({ at: "map", recipeId: view.recipeId, pipeline, mapNodeId })}
    />
  );
}

function PipelinesHome({
  apiBaseUrl,
  bearerToken,
  investigationId,
  onOpen,
}: PipelineStudioProps & { onOpen: (recipe: StudioRecipeDraft) => void }) {
  const [drafts, setDrafts] = useState<StudioRecipeDraft[] | null>(null);
  const [label, setLabel] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Every recipe at every status but superseded: a published pipeline stays here to run again,
    // schedule or release held rows from, and a flagged one to republish.
    fetchRecipeRegistry(apiBaseUrl, bearerToken, investigationId)
      .then((found) => !cancelled && setDrafts(found.filter((r) => r.status !== "superseded")))
      .catch((err: unknown) => {
        if (!cancelled) setProblem(err instanceof Error ? err.message : "The pipelines could not be read.");
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);

  async function create() {
    setBusy(true);
    setProblem(null);
    try {
      // `connector_profile` is required at creation; the generic CSV profile is the neutral
      // starting point the source panel then changes.
      const made = await createDraft(apiBaseUrl, bearerToken, investigationId, {
        label: label.trim(),
        connector_profile: "generic-csv",
      });
      onOpen(made);
    } catch (err: unknown) {
      setProblem(err instanceof Error ? err.message : "The pipeline could not be created.");
      setBusy(false);
    }
  }

  return (
    <div style={{ padding: "var(--sp-16)", display: "grid", gap: "var(--sp-16)", alignContent: "start" }}>
      <p className="label" style={{ margin: 0 }}>
        A pipeline is one source's journey into this dataset's graph: a domain model, the source, its
        profile, its mapping, and the load. Name one and the canvas starts you with that chain. Test it,
        then deploy it; it runs from the Runs tab.
      </p>
      <section aria-label="New pipeline" style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
        <Input
          aria-label="Pipeline name"
          placeholder="Name the pipeline"
          value={label}
          maxLength={200}
          onChange={(e) => setLabel(e.target.value)}
        />
        <Button variant="primary" disabled={!label.trim() || busy} onClick={() => void create()}>
          New pipeline
        </Button>
      </section>
      {problem && <p role="alert">{problem}</p>}
      <section aria-label="Pipelines" style={{ display: "grid", gap: "var(--sp-4)" }}>
        {drafts === null && !problem && <p className="label">Reading the pipelines…</p>}
        {drafts?.length === 0 && <p className="label">No pipelines yet. Name one above — "Carrier B phone records", say — and set up its source on the canvas.</p>}
        <ul role="list" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
          {(drafts ?? []).map((draft) => (
            <li key={`${draft.recipe_id}:${draft.version}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--sp-8)" }}>
              <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>
                {draft.label}
                <span style={{ color: "var(--text-tertiary)" }}>{` · v${draft.version} · ${statusWords(draft.status)}`}</span>
              </span>
              <Button aria-label={`Open ${draft.label}`} onClick={() => onOpen(draft)}>
                Open
              </Button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}


function PipelineEditor({
  apiBaseUrl,
  bearerToken,
  investigationId,
  recipeId,
  initialSelectedId,
  username,
  onChanged,
  onHome,
  onOpenMap,
}: PipelineStudioProps & {
  recipeId: string;
  initialSelectedId: string | null;
  onHome: () => void;
  onOpenMap: (pipeline: PipelineGraph, mapNodeId: string) => void;
}) {
  const [draft, setDraft] = useState<StudioRecipeDraft | null>(null);
  const [pipeline, setPipeline] = useState<PipelineGraph | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(initialSelectedId);
  const [pane, setPane] = useState<DrawerPane>({ at: "node", view: "settings" });
  const [mode, setMode] = useState<StudioMode>(() => readStudioMode(username));
  const [problems, setProblems] = useState<string[]>([]);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchDraft(apiBaseUrl, bearerToken, investigationId, recipeId)
      .then((found) => {
        if (cancelled) return;
        setDraft(found);
        setPipeline(found.pipeline ?? { nodes: [], edges: [] });
      })
      .catch((err: unknown) => {
        if (!cancelled) setProblems([err instanceof Error ? err.message : "The pipeline could not be read."]);
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, recipeId]);

  async function save(next: PipelineGraph) {
    setBusy(true);
    setSaid(null);
    try {
      const outcome = await savePipeline(apiBaseUrl, bearerToken, investigationId, recipeId, next);
      if (outcome.kind === "invalid") {
        setProblems(outcome.problems);
      } else {
        setProblems([]);
        setDraft(outcome.draft);
        setPipeline(outcome.draft.pipeline ?? next);
        setSaid("Saved.");
      }
    } catch (err: unknown) {
      setProblems([err instanceof Error ? err.message : "The pipeline could not be saved."]);
    } finally {
      setBusy(false);
    }
  }

  if (!pipeline || !draft) {
    return (
      <div style={{ padding: "var(--sp-16)" }}>
        {problems.length > 0 ? <p role="alert">{problems[0]}</p> : <p className="label">Reading the pipeline…</p>}
      </div>
    );
  }

  const selected = (pipeline.nodes ?? []).find((n) => n.id === selectedId) ?? null;
  const maps = (pipeline.nodes ?? []).filter((n) => n.kind === "map");
  const change = (next: PipelineGraph) => {
    setPipeline(next);
    void save(next);
  };
  const choose = (node: PipelineNode) => {
    setSelectedId(node.id);
    setPane({ at: "node", view: "settings" });
  };
  const switchMode = (next: StudioMode) => {
    setMode(next);
    writeStudioMode(username, next);
  };

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-16)", padding: "var(--sp-16)", alignItems: "start" }}>
      <div style={{ flex: "1 1 480px", display: "grid", gap: "var(--sp-12)", minWidth: 0 }}>
        <header style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}>
          <Button onClick={onHome}>Pipelines</Button>
          <h2 style={{ margin: 0, fontSize: "var(--fs-16)" }}>{draft.label}</h2>
          <span className="label">{`v${draft.version} · ${statusWords(draft.status)}`}</span>
          <span style={{ flex: 1 }} />
          {/* ADR-140 decision 3 and Amendment 1.3: two modes over one pipeline, guided by default, a
              per-person preference. */}
          <div role="group" aria-label="Mode" style={{ display: "flex", gap: "var(--sp-4)" }}>
            <Button aria-pressed={mode === "guided"} onClick={() => switchMode("guided")}>
              Guided
            </Button>
            <Button aria-pressed={mode === "expert"} onClick={() => switchMode("expert")}>
              Expert
            </Button>
          </div>
          <Button onClick={() => setPane({ at: "checks" })}>Load rules</Button>
          <Button onClick={() => setPane({ at: "test" })}>Test</Button>
          <Button variant="primary" onClick={() => setPane({ at: "deploy" })}>
            Deploy
          </Button>
        </header>
        <div role="toolbar" aria-label="Pipeline stages" style={{ display: "flex", gap: "var(--sp-4)", flexWrap: "wrap" }}>
          <Button disabled={busy} onClick={() => change(addSourceChain(pipeline, "New source"))}>
            + Source
          </Button>
          <Button
            disabled={busy || maps.length === 0}
            onClick={() => change(addExtractAfter(pipeline, maps[maps.length - 1]!.id))}
          >
            + Extract
          </Button>
          <Button
            disabled={busy || maps.length === 0}
            onClick={() => change(addEnrichAfter(pipeline, maps[maps.length - 1]!.id))}
          >
            + Enrich
          </Button>
          <Button
            // ADR-140 decision 3: guided mode shows an expert step read-only, and removing it, or the
            // step that feeds it, is an edit of it; the reviews of L1.2 found Remove enabled for both
            // (7 November 2026).
            disabled={
              busy || !selected || selected.kind === "domain_model" || (mode === "guided" && guidedMayNotRemove(pipeline, selected))
            }
            onClick={() => {
              if (!selected) return;
              setSelectedId(null);
              change(removeNode(pipeline, selected.id));
            }}
          >
            Remove selected
          </Button>
        </div>
        {problems.length > 0 && (
          <div role="alert" style={{ display: "grid", gap: "var(--sp-2)" }}>
            {problems.map((p) => (
              <p key={p} style={{ margin: 0, color: "var(--text-secondary)" }}>
                {p}
              </p>
            ))}
          </div>
        )}
        {said && (
          <p role="status" className="label" style={{ margin: 0 }}>
            {said}
          </p>
        )}
        {mode === "guided" ? (
          <>
            <GuidedSteps pipeline={pipeline} selectedId={selectedId} onSelect={choose} />
            {/* The picture holds nothing to press, so its scroll box takes focus itself (WCAG 2.1.1,
                axe's scrollable-region-focusable) for a keyboard to scroll a wide pipeline. */}
            <div style={{ overflow: "auto" }} tabIndex={0} role="region" aria-label="Pipeline picture">
              <PipelineCanvas pipeline={pipeline} selectedId={selectedId} onSelect={choose} readOnly />
            </div>
          </>
        ) : (
          <div style={{ overflow: "auto" }}>
            <PipelineCanvas pipeline={pipeline} selectedId={selectedId} onSelect={choose} />
          </div>
        )}
      </div>
      <NodeDrawer
        apiBaseUrl={apiBaseUrl}
        bearerToken={bearerToken}
        investigationId={investigationId}
        recipeId={recipeId}
        draft={draft}
        pipeline={pipeline}
        node={selected}
        pane={pane}
        mode={mode}
        busy={busy}
        onPane={setPane}
        onClose={() => (pane.at === "node" ? setSelectedId(null) : setPane({ at: "node", view: "settings" }))}
        onChange={change}
        onDraft={setDraft}
        onOpenMapEditor={() => selected && onOpenMap(pipeline, selected.id)}
        onChanged={onChanged}
      />
    </div>
  );
}
