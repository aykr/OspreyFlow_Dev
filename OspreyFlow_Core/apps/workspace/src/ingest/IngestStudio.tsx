// The Ingest Studio's own stage navigation — `spec/09_INGEST_STUDIO.md` §1:
// "The five stages are navigable in any order once a source is connected."
// All five stages exist now; Profile/Map/Verify/Publish tabs only ever
// activate once the active draft's own gates say so — the same gates each
// screen's own "Continue" button already enforces, checked again here
// since a tab click bypasses that button.
import { useEffect, useState } from "react";

import type { StudioRecipeDraft } from "../../../../packages/schemas/generated";
import { AddFiles } from "../content/AddFiles";
import { Tabs } from "../design/primitives/Tabs";
import { CaseSwitcher } from "../investigation/CaseSwitcher";
import { ConnectScreen } from "./ConnectScreen";
import { PipelineCanvas } from "./dag/PipelineCanvas";
import { fetchDraft } from "./api";
import { MapScreen } from "./map/MapScreen";
import { ProfileScreen } from "./ProfileScreen";
import { PublishScreen } from "./publish/PublishScreen";
import { VerifyScreen } from "./verify/VerifyScreen";

export interface IngestStudioProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** Publish's own "Run now" action (§6, §8's `loader` role) attributes a
   * load to an investigation for analytics filtering — `null` before the
   * host has one yet (mirrors `App.tsx`'s own `investigationId` state,
   * which starts `null` until the first `POST /v1/investigations` lands). */
  investigationId: string | null;
  /** Switching to another case, or one just created, from the studio (owner, 29 September 2026). */
  onOpenCase: (id: string) => void;
}

type Stage = "connect" | "profile" | "map" | "verify" | "publish" | "files" | "pipeline";

export function IngestStudio({
  apiBaseUrl,
  bearerToken,
  investigationId,
  onOpenCase,
}: IngestStudioProps) {
  const [stage, setStage] = useState<Stage>("connect");
  const [activeDraft, setActiveDraft] = useState<StudioRecipeDraft | null>(null);

  function goToProfile(recipeId: string) {
    if (activeDraft?.recipe_id !== recipeId || !activeDraft.ready_for_profile) return;
    setStage("profile");
  }

  // Map (§4) is reachable once Profile is, the same `ready_for_profile`
  // gate — §3: "the studio does not let you map until it has run", and
  // Profile is what runs it.
  function goToMap() {
    if (!activeDraft?.ready_for_profile) return;
    setStage("map");
  }

  // Verify (§5) needs everything Map needs, plus a saved row template —
  // there is nothing to dry-run without one (mirrors the backend's own
  // `row_template_missing` gate).
  function goToVerify() {
    if (!activeDraft?.ready_for_profile || !activeDraft.row_template) return;
    setStage("verify");
  }

  // Publish (§6) is reachable regardless of `activeDraft` — unlike
  // Profile/Map/Verify, which continue a draft still in this session,
  // Publish is also where an already-published recipe gets revisited
  // (to schedule it, reopen it, or run it) days later in a fresh session
  // that never went through Connect at all. `PublishScreen` itself offers
  // the recipe registry picker for that case.
  function goToPublish() {
    setStage("publish");
  }

  // ADR-099 Amendment 3: a recipe and a source file belong to the dataset of the case they are
  // made in, so the studio works only within a case.
  if (!investigationId) {
    return (
      <p className="label" style={{ padding: "var(--sp-16)" }}>
        Open a case to use the Ingest Studio: what it loads goes into the case&apos;s data.
      </p>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      {investigationId && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-16)",
            padding: "var(--sp-8) var(--sp-16)",
            borderBottom: "1px solid var(--border-subtle)",
          }}
        >
          <span className="label">Data loaded from this studio goes into</span>
          <CaseSwitcher
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            currentId={investigationId}
            onOpen={onOpenCase}
          />
        </div>
      )}
      <Tabs
        tabs={[
          { id: "connect", label: "Connect" },
          { id: "profile", label: "Profile" },
          { id: "map", label: "Map" },
          { id: "verify", label: "Verify" },
          { id: "publish", label: "Publish" },
          // ADR-094 step 3, spec 09 §7: the unstructured path, a screen of its own.
          ...(investigationId ? [{ id: "files", label: "Files" }] : []),
          // ADR-108 phase A: the recipe as a pipeline, read-only; phase B makes it the editor.
          ...(activeDraft ? [{ id: "pipeline", label: "Pipeline" }] : []),
        ]}
        activeId={stage}
        onChange={(id) => {
          if (id === "profile") {
            if (!activeDraft?.ready_for_profile) return;
            setStage("profile");
          } else if (id === "map") {
            goToMap();
          } else if (id === "verify") {
            goToVerify();
          } else if (id === "publish") {
            goToPublish();
          } else if (id === "files") {
            setStage("files");
          } else if (id === "pipeline") {
            if (activeDraft) setStage("pipeline");
          } else {
            setStage("connect");
          }
        }}
      />
      <div style={{ flex: 1, minHeight: 0 }}>
        {/* Kept mounted (hidden, not unmounted) while on another stage —
            unmounting would drop each screen's own in-progress state, so
            switching tabs mid-edit doesn't land on an empty form or an
            empty template. */}
        <div style={{ display: stage === "connect" ? "contents" : "none" }}>
          <ConnectScreen
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            investigationId={investigationId}
            onDraftChange={setActiveDraft}
            onContinueToProfile={goToProfile}
          />
        </div>
        {stage === "files" && investigationId && (
          <div style={{ padding: "var(--sp-16)", maxWidth: 560 }}>
            <AddFiles
              apiBaseUrl={apiBaseUrl}
              bearerToken={bearerToken}
              investigationId={investigationId}
              // The canvas is not open here; the case's view gains each Document when it opens.
              onDelta={() => undefined}
              onClose={() => setStage("connect")}
            />
          </div>
        )}
        {stage === "profile" && activeDraft && (
          <ProfileScreen
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            investigationId={investigationId}
            recipeId={activeDraft.recipe_id}
            onBack={() => setStage("connect")}
          />
        )}
        {stage === "map" && activeDraft && (
          <MapScreen
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            investigationId={investigationId}
            recipeId={activeDraft.recipe_id}
            onBack={() => setStage("connect")}
            onDraftChange={setActiveDraft}
          />
        )}
        {stage === "verify" && activeDraft && (
          <VerifyScreen
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            investigationId={investigationId}
            recipeId={activeDraft.recipe_id}
            onBack={() => setStage("connect")}
          />
        )}
        {stage === "pipeline" && activeDraft && (
          <PipelineStage
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            investigationId={investigationId}
            recipeId={activeDraft.recipe_id}
          />
        )}
        {stage === "publish" && (
          <PublishScreen
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            recipeId={activeDraft?.recipe_id ?? null}
            investigationId={investigationId}
            onBack={() => setStage("connect")}
            onSelectRecipe={setActiveDraft}
            onReopenedForEditing={(reopened) => {
              setActiveDraft(reopened);
              setStage("map");
            }}
          />
        )}
      </div>
    </div>
  );
}

/** ADR-108 phase A: the draft read fresh (its pipeline is derived at read time), drawn read-only.
 * Phase B replaces this stage with the editable canvas. */
function PipelineStage({
  apiBaseUrl,
  bearerToken,
  investigationId,
  recipeId,
}: {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  recipeId: string;
}) {
  const [draft, setDraft] = useState<StudioRecipeDraft | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setDraft(null);
    setProblem(null);
    fetchDraft(apiBaseUrl, bearerToken, investigationId, recipeId)
      .then((found) => !cancelled && setDraft(found))
      .catch((err: unknown) => {
        if (!cancelled) setProblem(err instanceof Error ? err.message : "The recipe could not be read.");
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, recipeId]);
  if (problem) return <p role="alert" style={{ padding: "var(--sp-16)" }}>{problem}</p>;
  if (!draft) return <p className="label" style={{ padding: "var(--sp-16)" }}>Reading the recipe…</p>;
  if (!draft.pipeline) return <p className="label" style={{ padding: "var(--sp-16)" }}>This recipe has no pipeline to show.</p>;
  return (
    <div style={{ padding: "var(--sp-16)", overflow: "auto" }}>
      <PipelineCanvas pipeline={draft.pipeline} />
    </div>
  );
}
