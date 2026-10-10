// The Ingest Studio as ADR-108 phase B ships it: a pipelines home, the canvas as the one editing
// surface, and each stage's editor opened from its node — the 1–9 wizard is gone (ruling Q6).
// The save gate stays the server's: a violation comes back as words and is shown, never swallowed.
import { useEffect, useState } from "react";

import type {
  DomainPackEntry,
  PipelineGraph,
  PipelineNode,
  StudioRecipeDraft,
} from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { Select } from "../../design/primitives/Select";
import {
  createDraft,
  fetchDomainPacks,
  fetchDraft,
  listDrafts,
  savePipeline,
  updateDraft,
} from "../api";
import { MapScreen } from "../map/MapScreen";
import { ProfileScreen } from "../ProfileScreen";
import { PublishScreen } from "../publish/PublishScreen";
import { VerifyScreen } from "../verify/VerifyScreen";
import { PipelineCanvas } from "./PipelineCanvas";
import {
  addEnrichAfter,
  addExtractAfter,
  addSourceChain,
  removeNode,
  withNodeConfig,
} from "./pipelineGraphEdit";

export interface PipelineStudioProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
}

type View =
  | { at: "home" }
  | { at: "canvas"; recipeId: string }
  | { at: "profile" | "map" | "verify" | "publish"; recipeId: string };

export function PipelineStudio({ apiBaseUrl, bearerToken, investigationId }: PipelineStudioProps) {
  const [view, setView] = useState<View>({ at: "home" });

  if (view.at === "home") {
    return (
      <PipelinesHome
        apiBaseUrl={apiBaseUrl}
        bearerToken={bearerToken}
        investigationId={investigationId}
        onOpen={(recipeId) => setView({ at: "canvas", recipeId })}
      />
    );
  }
  const stage = { apiBaseUrl, bearerToken, investigationId, recipeId: view.recipeId };
  const back = () => setView({ at: "canvas", recipeId: view.recipeId });
  if (view.at === "profile") return <ProfileScreen {...stage} onBack={back} />;
  if (view.at === "map") return <MapScreen {...stage} onBack={back} />;
  if (view.at === "verify") return <VerifyScreen {...stage} onBack={back} />;
  if (view.at === "publish") {
    return (
      <PublishScreen
        apiBaseUrl={apiBaseUrl}
        bearerToken={bearerToken}
        investigationId={investigationId}
        recipeId={view.recipeId}
        onBack={back}
        onSelectRecipe={() => undefined}
        onReopenedForEditing={() => back()}
      />
    );
  }
  return (
    <PipelineEditor
      apiBaseUrl={apiBaseUrl}
      bearerToken={bearerToken}
      investigationId={investigationId}
      recipeId={view.recipeId}
      onHome={() => setView({ at: "home" })}
      onOpenStage={(at) => setView({ at, recipeId: view.recipeId })}
    />
  );
}

function PipelinesHome({
  apiBaseUrl,
  bearerToken,
  investigationId,
  onOpen,
}: PipelineStudioProps & { onOpen: (recipeId: string) => void }) {
  const [drafts, setDrafts] = useState<StudioRecipeDraft[] | null>(null);
  const [label, setLabel] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listDrafts(apiBaseUrl, bearerToken, investigationId)
      .then((found) => !cancelled && setDrafts(found))
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
      onOpen(made.recipe_id);
    } catch (err: unknown) {
      setProblem(err instanceof Error ? err.message : "The pipeline could not be created.");
      setBusy(false);
    }
  }

  return (
    <div style={{ padding: "var(--sp-16)", display: "grid", gap: "var(--sp-16)", alignContent: "start" }}>
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
        {drafts?.length === 0 && <p className="label">No pipelines yet. Name one above to begin.</p>}
        <ul role="list" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
          {(drafts ?? []).map((draft) => (
            <li key={`${draft.recipe_id}:${draft.version}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--sp-8)" }}>
              <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>
                {draft.label}
                <span style={{ color: "var(--text-tertiary)" }}>{` · v${draft.version} · ${draft.status}`}</span>
              </span>
              <Button aria-label={`Open ${draft.label}`} onClick={() => onOpen(draft.recipe_id)}>
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
  onHome,
  onOpenStage,
}: PipelineStudioProps & {
  recipeId: string;
  onHome: () => void;
  onOpenStage: (at: "profile" | "map" | "verify" | "publish") => void;
}) {
  const [draft, setDraft] = useState<StudioRecipeDraft | null>(null);
  const [pipeline, setPipeline] = useState<PipelineGraph | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
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

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: "var(--sp-16)", padding: "var(--sp-16)", alignItems: "start" }}>
      <div style={{ display: "grid", gap: "var(--sp-12)", minWidth: 0 }}>
        <header style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}>
          <Button onClick={onHome}>Pipelines</Button>
          <h2 style={{ margin: 0, fontSize: "var(--fs-16)" }}>{draft.label}</h2>
          <span className="label">{`v${draft.version} · ${draft.status}`}</span>
          <span style={{ flex: 1 }} />
          <Button onClick={() => onOpenStage("verify")}>Verify</Button>
          <Button onClick={() => onOpenStage("publish")}>Publish</Button>
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
            disabled={busy || !selected || selected.kind === "domain_model"}
            onClick={() => selected && change(removeNode(pipeline, selected.id))}
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
        <div style={{ overflow: "auto" }}>
          <PipelineCanvas pipeline={pipeline} selectedId={selectedId} onSelect={(n) => setSelectedId(n.id)} />
        </div>
      </div>
      <aside aria-label="Stage settings" style={{ display: "grid", gap: "var(--sp-8)", alignContent: "start" }}>
        {!selected && <p className="label">Choose a stage on the canvas to set it up.</p>}
        {selected?.kind === "domain_model" && (
          <DomainPanel
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            node={selected}
            disabled={busy}
            onApply={(config) => change(withNodeConfig(pipeline, selected.id, config))}
          />
        )}
        {selected?.kind === "source" && (
          <SourcePanel
            draft={draft}
            node={selected}
            disabled={busy}
            onApply={async (config) => {
              change(withNodeConfig(pipeline, selected.id, config));
              // The first source also carries the draft-level fields the engine reads today.
              const first = (pipeline.nodes ?? []).find((n) => n.kind === "source");
              if (first && first.id === selected.id) {
                const updated = await updateDraft(apiBaseUrl, bearerToken, investigationId, recipeId, {
                  label: draft.label,
                  connector_profile:
                    (config.connector_profile as string) || draft.connector_profile || "generic-csv",
                  source_location: (config.source_location as string) || null,
                });
                setDraft(updated);
              }
            }}
          />
        )}
        {selected?.kind === "profile" && (
          <StagePanel title="Profile" words="Run and read the source's profile.">
            <Button onClick={() => onOpenStage("profile")}>Open profile</Button>
          </StagePanel>
        )}
        {selected?.kind === "map" && (
          <StagePanel title="Map" words="Bind the source's fields to the domain model.">
            <Button onClick={() => onOpenStage("map")}>Open map editor</Button>
          </StagePanel>
        )}
        {selected?.kind === "extract" && (
          <ExtractPanel
            node={selected}
            disabled={busy}
            onApply={(config) => change(withNodeConfig(pipeline, selected.id, config))}
          />
        )}
        {selected?.kind === "enrich" && (
          <EnrichPanel
            node={selected}
            disabled={busy}
            onApply={(config) => change(withNodeConfig(pipeline, selected.id, config))}
          />
        )}
        {selected?.kind === "load" && (
          <StagePanel title="Load" words={`Writes into this case's dataset${draft.dataset_id ? ` (${draft.dataset_id})` : ""}, idempotent and revertible by load.`} />
        )}
      </aside>
    </div>
  );
}

function StagePanel({ title, words, children }: { title: string; words: string; children?: React.ReactNode }) {
  return (
    <section aria-label={`${title} settings`} style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)" }}>{title}</h3>
      <p className="label" style={{ margin: 0 }}>
        {words}
      </p>
      {children}
    </section>
  );
}

function DomainPanel({
  apiBaseUrl,
  bearerToken,
  node,
  disabled,
  onApply,
}: {
  apiBaseUrl: string;
  bearerToken: string;
  node: PipelineNode;
  disabled: boolean;
  onApply: (config: Record<string, unknown>) => void;
}) {
  const [packs, setPacks] = useState<DomainPackEntry[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetchDomainPacks(apiBaseUrl, bearerToken)
      .then((found) => !cancelled && setPacks(found))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken]);
  const current = (node.config?.pack as string) ?? "pole";
  return (
    <section aria-label="Domain model settings" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)" }}>Domain model</h3>
      <p className="label" style={{ margin: 0 }}>
        What this pipeline's data means. The pack adds its types over the POLE core.
      </p>
      <div role="radiogroup" aria-label="Domain pack" style={{ display: "grid", gap: "var(--sp-4)" }}>
        {packs.map((pack) => (
          <label key={pack.name} style={{ display: "grid", gap: "var(--sp-2)" }}>
            <span style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
              <input
                type="radio"
                name="domain-pack"
                checked={current === pack.name}
                disabled={disabled}
                onChange={() => onApply({ ...node.config, pack: pack.name })}
              />
              {pack.label}
            </span>
            {(pack.entity_types?.length ?? 0) > 0 && (
              <span className="label" style={{ paddingLeft: "var(--sp-24)" }}>
                {`Adds ${pack.entity_types!.join(", ")}`}
              </span>
            )}
          </label>
        ))}
      </div>
    </section>
  );
}

function SourcePanel({
  draft,
  node,
  disabled,
  onApply,
}: {
  draft: StudioRecipeDraft;
  node: PipelineNode;
  disabled: boolean;
  onApply: (config: Record<string, unknown>) => void | Promise<void>;
}) {
  const [connector, setConnector] = useState<string>(
    (node.config?.connector_profile as string) ?? draft.connector_profile ?? "",
  );
  const [location, setLocation] = useState<string>(
    (node.config?.source_location as string) ?? draft.source_location ?? "",
  );
  return (
    <section aria-label="Source settings" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)" }}>Source</h3>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Connector profile</span>
        <Input aria-label="Connector profile" value={connector} onChange={(e) => setConnector(e.target.value)} />
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Source location</span>
        <Input aria-label="Source location" value={location} onChange={(e) => setLocation(e.target.value)} />
      </label>
      <Button
        disabled={disabled}
        onClick={() =>
          void onApply({ ...node.config, connector_profile: connector || null, source_location: location || null })
        }
      >
        Apply source settings
      </Button>
    </section>
  );
}

/** ADR-108 rulings Q1–Q3: the extract stage's declared settings — recogniser or model, the media
 * kind, where findings go (queue by default), and the handling override (below source needs an
 * Author and a reason; the engine enforces it in phase C, the words are honest now). */
function ExtractPanel({
  node,
  disabled,
  onApply,
}: {
  node: PipelineNode;
  disabled: boolean;
  onApply: (config: Record<string, unknown>) => void;
}) {
  const config = node.config ?? {};
  const [library, setLibrary] = useState<string>((config.library as string) ?? "stanza");
  const [media, setMedia] = useState<string>((config.media as string) ?? "text");
  const [output, setOutput] = useState<string>((config.output as string) ?? "review_queue");
  return (
    <section aria-label="Extract settings" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)" }}>Extract</h3>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Library</span>
        <Select aria-label="Extraction library" value={library} onChange={(e) => setLibrary(e.target.value)}>
          <option value="stanza">Stanza (fast recogniser)</option>
          <option value="spacy">spaCy (fast recogniser)</option>
          <option value="transformers">Transformers NER (fast recogniser)</option>
          <option value="model">The deployment's language model (deep)</option>
          <option value="whisper">faster-whisper (audio transcription)</option>
          <option value="vision">Qwen2-VL (image and video)</option>
        </Select>
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Media kind</span>
        <Select aria-label="Media kind" value={media} onChange={(e) => setMedia(e.target.value)}>
          <option value="text">Document (text)</option>
          <option value="image">Image</option>
          <option value="audio">Audio</option>
        </Select>
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Findings go to</span>
        <Select aria-label="Findings go to" value={output} onChange={(e) => setOutput(e.target.value)}>
          <option value="review_queue">The review queue (bulk accept)</option>
          <option value="inferred_graph">The graph, as inferred — never asserted</option>
        </Select>
      </label>
      <p className="label" style={{ margin: 0 }}>
        Findings inherit the source&apos;s marking and legal basis. Marking below the source needs an
        Author and a written reason, and the run report says so.
      </p>
      <Button disabled={disabled} onClick={() => onApply({ ...config, library, media, output })}>
        Apply extract settings
      </Button>
    </section>
  );
}

/** ADR-108 ruling Q5: local gazetteers first; an online provider only from the deployment's
 * allow-list, and a run that used one says so. */
function EnrichPanel({
  node,
  disabled,
  onApply,
}: {
  node: PipelineNode;
  disabled: boolean;
  onApply: (config: Record<string, unknown>) => void;
}) {
  const config = node.config ?? {};
  const [geocoder, setGeocoder] = useState<string>((config.geocoder as string) ?? "local_gazetteer");
  return (
    <section aria-label="Enrich settings" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)" }}>Enrich</h3>
      <p className="label" style={{ margin: 0 }}>
        Parses unstructured addresses (deepparse) and geocodes them for the map.
      </p>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Geocode against</span>
        <Select aria-label="Geocode against" value={geocoder} onChange={(e) => setGeocoder(e.target.value)}>
          <option value="local_gazetteer">The loaded gazetteers (on this deployment)</option>
          <option value="online_allowlist">An allowed online provider — disclosed per run</option>
        </Select>
      </label>
      <Button disabled={disabled} onClick={() => onApply({ ...config, geocoder })}>
        Apply enrich settings
      </Button>
    </section>
  );
}
