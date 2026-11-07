// The drawer beside the pipeline (ADR-108 Amendment 6.1; ADR-140 decisions 3 and 14; redesign brief
// §6): choosing a node opens its editor here, and the canvas, or guided mode's numbered list, stays
// in view beside it. Nothing replaces the canvas. A node's drawer has two views, its *Settings* and
// its *Preview* (`NodePreview`); the pipeline's own *Load rules*, *Test* and *Deploy* open here too,
// as do the source's own settings and the profile, each the existing screen hosted whole with no
// "Back to the pipeline" (there is nothing to go back to). The one exception is Map: its editor
// needs the width, so it collapses the pipeline to a strip across the top (`MapEditor`, brief §6.5)
// rather than replacing it.
import type {
  PipelineGraph,
  PipelineNode,
  StudioRecipeDraft,
} from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { ChecksScreen } from "../checks/ChecksScreen";
import { ConnectScreen } from "../ConnectScreen";
import { ProfileScreen } from "../ProfileScreen";
import { PublishScreen } from "../publish/PublishScreen";
import { SourceChooser } from "../sources/SourceChooser";
import { VerifyScreen } from "../verify/VerifyScreen";
import { isExpertStep } from "./GuidedSteps";
import { NodePreview } from "./NodePreview";
import { KIND_NAMES } from "./PipelineCanvas";
import { withNodeConfig } from "./pipelineGraphEdit";
import { DomainPanel, EnrichPanel, ExtractPanel, SourcePanel, StagePanel } from "./stagePanels";
import type { StudioMode } from "./studioMode";

/** What the drawer holds: a node (its settings or preview), or one of the pipeline's own screens. */
export type DrawerPane =
  | { at: "node"; view: "settings" | "preview" }
  | { at: "connect" | "profile" | "checks" | "test" | "deploy" };

const PANE_TITLES: Record<Exclude<DrawerPane["at"], "node">, string> = {
  connect: "The draft's own settings",
  profile: "Profile",
  checks: "Load rules",
  test: "Test",
  deploy: "Deploy",
};

export interface NodeDrawerProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  recipeId: string;
  draft: StudioRecipeDraft;
  pipeline: PipelineGraph;
  node: PipelineNode | null;
  pane: DrawerPane;
  mode: StudioMode;
  busy: boolean;
  onPane: (pane: DrawerPane) => void;
  /** Close: a pipeline screen goes back to the node; a node is let go. */
  onClose: () => void;
  onChange: (next: PipelineGraph) => void;
  onDraft: (draft: StudioRecipeDraft) => void;
  onOpenMapEditor: () => void;
  /** Deployed, reopened or run: the readiness strip and the Runs tab read again. */
  onChanged?: () => void;
}

export function NodeDrawer(props: NodeDrawerProps) {
  const { pane, node, onPane, onClose } = props;
  const title =
    pane.at === "node" ? (node ? `${KIND_NAMES[node.kind] ?? node.kind}: ${node.label}` : null) : PANE_TITLES[pane.at];
  const wide = pane.at !== "node";
  return (
    <aside
      aria-label="Drawer"
      style={{
        flex: wide ? "1 1 520px" : "1 1 340px",
        maxWidth: wide ? undefined : 480,
        minWidth: 0,
        display: "grid",
        gap: "var(--sp-8)",
        alignContent: "start",
        borderLeft: "1px solid var(--border-subtle)",
        paddingLeft: "var(--sp-16)",
      }}
    >
      {title === null ? (
        <p className="label">Choose a step to set it up, preview it, or Test the whole pipeline.</p>
      ) : (
        <header style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center", flexWrap: "wrap" }}>
          {/* A hosted screen names itself in its own heading; the drawer does not say it twice. */}
          {pane.at === "node" ? (
            <h3 style={{ margin: 0, fontSize: "var(--fs-14)", flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>{title}</h3>
          ) : (
            <span style={{ flex: 1 }} />
          )}
          <Button aria-label="Close the drawer" onClick={onClose}>
            Close
          </Button>
        </header>
      )}
      {pane.at === "node" && node && (
        <>
          <div role="group" aria-label="Drawer view" style={{ display: "flex", gap: "var(--sp-4)" }}>
            <Button aria-pressed={pane.view === "settings"} onClick={() => onPane({ at: "node", view: "settings" })}>
              Settings
            </Button>
            <Button aria-pressed={pane.view === "preview"} onClick={() => onPane({ at: "node", view: "preview" })}>
              Preview
            </Button>
          </div>
          {pane.view === "preview" ? (
            <NodePreview
              key={node.id}
              apiBaseUrl={props.apiBaseUrl}
              bearerToken={props.bearerToken}
              investigationId={props.investigationId}
              recipeId={props.recipeId}
              node={node}
            />
          ) : (
            <NodeSettings {...props} node={node} />
          )}
        </>
      )}
      {pane.at === "connect" && (
        <ConnectScreen
          apiBaseUrl={props.apiBaseUrl}
          bearerToken={props.bearerToken}
          investigationId={props.investigationId}
          recipeId={props.recipeId}
          onDraftChange={(d) => d && props.onDraft(d)}
        />
      )}
      {pane.at === "profile" && (
        <ProfileScreen apiBaseUrl={props.apiBaseUrl} bearerToken={props.bearerToken} investigationId={props.investigationId} recipeId={props.recipeId} />
      )}
      {pane.at === "checks" && (
        <ChecksScreen apiBaseUrl={props.apiBaseUrl} bearerToken={props.bearerToken} investigationId={props.investigationId} recipeId={props.recipeId} />
      )}
      {pane.at === "test" && (
        <VerifyScreen apiBaseUrl={props.apiBaseUrl} bearerToken={props.bearerToken} investigationId={props.investigationId} recipeId={props.recipeId} />
      )}
      {pane.at === "deploy" && (
        <PublishScreen
          apiBaseUrl={props.apiBaseUrl}
          bearerToken={props.bearerToken}
          investigationId={props.investigationId}
          recipeId={props.recipeId}
          onSelectRecipe={() => undefined}
          onReopenedForEditing={(d) => {
            props.onDraft(d);
            props.onChanged?.();
          }}
          onRan={props.onChanged}
        />
      )}
    </aside>
  );
}

function NodeSettings({
  apiBaseUrl,
  bearerToken,
  investigationId,
  draft,
  pipeline,
  node,
  mode,
  busy,
  onPane,
  onChange,
  onDraft,
  onOpenMapEditor,
}: NodeDrawerProps & { node: PipelineNode }) {
  const apply = (config: Record<string, unknown>) => onChange(withNodeConfig(pipeline, node.id, config));
  if (isExpertStep(node)) {
    // ADR-140 decision 3: an expert step reads whole in guided mode, read-only and labelled. Phase 8
    // builds its editor (and `write_sql_transforms`); until then it is read-only in both modes.
    return (
      <section aria-label="Expert step" style={{ display: "grid", gap: "var(--sp-8)" }}>
        <p className="label" style={{ margin: 0 }}>
          {mode === "guided"
            ? "An expert step: guided mode shows it read-only. Switch to expert mode to work with it."
            : "An expert step: it cannot be edited here yet."}
        </p>
        <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: "var(--sp-2) var(--sp-12)" }}>
          {Object.entries(node.config ?? {}).map(([key, value]) => (
            <div key={key} style={{ display: "contents" }}>
              <dt style={{ color: "var(--text-secondary)" }}>{key}</dt>
              <dd className="value" style={{ margin: 0, overflowWrap: "anywhere" }}>
                {value === null || value === undefined ? "—" : typeof value === "string" ? value : JSON.stringify(value)}
              </dd>
            </div>
          ))}
        </dl>
      </section>
    );
  }
  const firstSource = (pipeline.nodes ?? []).find((n) => n.kind === "source");
  switch (node.kind) {
    case "domain_model":
      return <DomainPanel apiBaseUrl={apiBaseUrl} bearerToken={bearerToken} node={node} disabled={busy} onApply={apply} />;
    case "source":
      return firstSource?.id === node.id ? (
        // The pipeline's first source carries the draft itself (ADR-140 Amendment 4: it names a
        // registered source, whose governance comes with it).
        <SourceChooser
          apiBaseUrl={apiBaseUrl}
          bearerToken={bearerToken}
          investigationId={investigationId}
          draft={draft}
          disabled={busy}
          onUsed={(updated, source) => {
            onDraft(updated);
            apply({ ...(node.config ?? {}), source_id: source.id });
          }}
          onOpenDraftSettings={() => onPane({ at: "connect" })}
        />
      ) : (
        <SourcePanel draft={draft} node={node} disabled={busy} onApply={apply} />
      );
    case "profile":
      return (
        <StagePanel title="Profile" words="Run and read the source's profile.">
          <Button onClick={() => onPane({ at: "profile" })}>Open profile</Button>
        </StagePanel>
      );
    case "map":
      return (
        <StagePanel title="Map" words="Bind the source's columns to the target model. The pipeline stays across the top.">
          <Button onClick={onOpenMapEditor}>Open map editor</Button>
        </StagePanel>
      );
    case "extract":
      return <ExtractPanel node={node} disabled={busy} onApply={apply} />;
    case "enrich":
      return <EnrichPanel node={node} disabled={busy} onApply={apply} />;
    case "load":
      return (
        <StagePanel
          title="Load"
          words={`Writes into this case's dataset${draft.dataset_id ? ` (${draft.dataset_id})` : ""}, idempotent and revertible by load.`}
        >
          <Button onClick={() => onPane({ at: "checks" })}>Open load rules</Button>
        </StagePanel>
      );
    default:
      return null;
  }
}
