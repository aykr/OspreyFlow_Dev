// The Ingest Studio's own stage navigation — `spec/09_INGEST_STUDIO.md` §1:
// "The five stages are navigable in any order once a source is connected."
// All five stages exist now; Profile/Map/Verify/Publish tabs only ever
// activate once the active draft's own gates say so — the same gates each
// screen's own "Continue" button already enforces, checked again here
// since a tab click bypasses that button.
import { useState } from "react";

import type { StudioRecipeDraft } from "../../../../packages/schemas/generated";
import { Tabs } from "../design/primitives/Tabs";
import { ConnectScreen } from "./ConnectScreen";
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
}

type Stage = "connect" | "profile" | "map" | "verify" | "publish";

export function IngestStudio({ apiBaseUrl, bearerToken, investigationId }: IngestStudioProps) {
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

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <Tabs
        tabs={[
          { id: "connect", label: "Connect" },
          { id: "profile", label: "Profile" },
          { id: "map", label: "Map" },
          { id: "verify", label: "Verify" },
          { id: "publish", label: "Publish" },
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
            onDraftChange={setActiveDraft}
            onContinueToProfile={goToProfile}
          />
        </div>
        {stage === "profile" && activeDraft && (
          <ProfileScreen
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            recipeId={activeDraft.recipe_id}
            onBack={() => setStage("connect")}
          />
        )}
        {stage === "map" && activeDraft && (
          <MapScreen
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            recipeId={activeDraft.recipe_id}
            onBack={() => setStage("connect")}
            onDraftChange={setActiveDraft}
          />
        )}
        {stage === "verify" && activeDraft && (
          <VerifyScreen
            apiBaseUrl={apiBaseUrl}
            bearerToken={bearerToken}
            recipeId={activeDraft.recipe_id}
            onBack={() => setStage("connect")}
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
