import type Graph from "graphology";
import type { EdgeTypeDef, Judgement, Node } from "../../../../packages/schemas/generated";
import { JudgementsPanel } from "../assessment/JudgementsPanel";
import { Panel } from "../design/primitives/Panel";
import { AccordionSection } from "../design/primitives/AccordionSection";
import { LinkDetails, type LinkDetailsProps } from "./LinkDetails";
import { LinkChange } from "./LinkChange";
import type { LinkChangeResult } from "./linkChangeApi";
import { LinkHistory } from "./LinkHistory";
import { LinkEvents } from "./LinkEvents";
import { eventsNoun, nounWords } from "./linkEventsApi";
import { displayValue } from "../search/searchOptions";
import { LinkNotes } from "./LinkNotes";
import { useEffect, useRef, useState } from "react";
import type { DocumentReaderView } from "../reader/readerApi";

function isResolutionLink(type: string): boolean {
  return type === "SAME_AS" || type === "NOT_SAME_AS";
}

export interface InspectorProps {
  node: Node | null;
  /** A selected link. While one is, the Inspector shows it instead of a node. */
  link?: LinkDetailsProps | null;
  /** What the link view needs to change a link and react to the link menu (ADR-080). Omitted, the
   * link is shown and noted but not offered a change. */
  linkEditing?: {
    edgeTypes: readonly EdgeTypeDef[];
    /** Each time one of these counts up, the matching part of the link view opens or takes focus. */
    openChangeSignal: number;
    openNoteSignal: number;
    openEventsSignal?: number;
    /** The link menu's *Show change history* (ADR-096: it opens that section). */
    openHistorySignal?: number;
    /** What the working set gained from an email (ADR-089 step 3), to apply to the view. */
    onDelta?: (delta: unknown) => void;
    /** Opens an email in the full-screen reader (ADR-092 Amendment 3). */
    onReadFullScreen?: (view: DocumentReaderView) => void;
    /** The timeline's brushed window, for the Emails list's *Put on the canvas* (ADR-095). */
    getEventsWindow?: () => { validFrom: string; validTo: string | null } | null;
    /** Told of a saved change so the new link can be put in the view. */
    onChanged: (result: LinkChangeResult) => void;
    /** The proposed types among `edgeTypes`, and what to do when one is proposed (ADR-090). */
    proposedTypes?: ReadonlySet<string>;
    onTypeProposed?: (definition: EdgeTypeDef) => void;
  };
  /** Phase 8 Stage 4c: the Judgements tab, `02_GLASS_FRONTEND.md` §9. `undefined` when the
   * caller has not wired assessment production up yet (an existing test harness) — the tab is
   * then simply not offered, the same optional-prop pattern `dimmedNodeIds`/`communityHulls`
   * already establish on `GlassCanvas` for exactly this reason. */
  assessment?: {
    apiBaseUrl: string;
    bearerToken: string;
    investigationId: string;
    workingSetGraph: Graph;
    onHighlightNodes: (nodeIds: string[]) => void;
    /** Told the full list of judgements each time the panel has fetched it, so the canvas can keep
     * the count beside each node current (ADR-070). */
    onJudgementsChange?: (judgements: Judgement[]) => void;
  };
}

type LinkPart = "details" | "change" | "notes" | "events" | "history";
type NodePart = "properties" | "provenance" | "source" | "judgements";

/** Which parts of a panel are open, starting from `initial`; `toggle` opens or closes one. */
function useOpenParts<T extends string>(initial: readonly T[]) {
  const [open, setOpen] = useState<ReadonlySet<T>>(() => new Set(initial));
  const toggle = (part: T) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(part)) next.delete(part);
      else next.add(part);
      return next;
    });
  const show = (part: T) => setOpen((current) => (current.has(part) ? current : new Set([...current, part])));
  return { isOpen: (part: T) => open.has(part), toggle, show };
}

/** A link-menu choice to open one part of the link view: which part, for which link, and a count so
 * the same request twice is seen twice. */
interface PartRequest {
  part: LinkPart;
  edgeId: string;
  n: number;
}

/** The Inspector (`spec/02_GLASS_FRONTEND.md` §2, ADR-096): every part folds away under its own
 * header, opening on the part read at a glance, a link's *Details* or a node's *Properties*; with no
 * node selected, *Judgements*. A link-menu choice opens its part. A folded part stays in the page,
 * so what is half-written in it is kept.
 *
 * **Judgements does not require a selected node**: assessment production is investigation-scoped,
 * not node-scoped (`02_GLASS_FRONTEND.md` §9). */
export function Inspector({ node, link, linkEditing, assessment }: InspectorProps) {
  // The link menu's counters only ever rise; a part opens when one rises, never on a later
  // selection just because a counter is above zero.
  const seen = useRef({ note: 0, change: 0, events: 0, history: 0 });
  const [request, setRequest] = useState<PartRequest | null>(null);
  const signals = {
    note: linkEditing?.openNoteSignal ?? 0,
    change: linkEditing?.openChangeSignal ?? 0,
    events: linkEditing?.openEventsSignal ?? 0,
    history: linkEditing?.openHistorySignal ?? 0,
  };
  const edgeId = link?.edge.id;
  useEffect(() => {
    const parts: Record<keyof typeof signals, LinkPart> = {
      note: "notes",
      change: "change",
      events: "events",
      history: "history",
    };
    for (const key of Object.keys(parts) as (keyof typeof signals)[]) {
      if (signals[key] > seen.current[key]) {
        seen.current[key] = signals[key];
        if (edgeId) setRequest({ part: parts[key], edgeId, n: signals[key] });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signals.note, signals.change, signals.events, signals.history, edgeId]);

  if (link) {
    return (
      <Panel title="Inspector" className="inspector">
        <LinkView key={link.edge.id} link={link} linkEditing={linkEditing} assessment={assessment} request={request} />
      </Panel>
    );
  }

  if (!node && !assessment) {
    return (
      <Panel title="Inspector" className="inspector">
        <p style={{ color: "var(--text-tertiary)", margin: 0 }}>Select a node to inspect it.</p>
      </Panel>
    );
  }

  return (
    <Panel title="Inspector" className="inspector">
      <NodeView key={node?.id ?? "no-node"} node={node} assessment={assessment} />
    </Panel>
  );
}

function LinkView({
  link,
  linkEditing,
  assessment,
  request,
}: Pick<InspectorProps, "linkEditing" | "assessment"> & {
  link: LinkDetailsProps;
  request: PartRequest | null;
}) {
  const parts = useOpenParts<LinkPart>(["details"]);
  // Opening *Change this link* opens the form itself, not a second button inside it.
  const [changeOpens, setChangeOpens] = useState(0);

  useEffect(() => {
    if (request && request.edgeId === link.edge.id) parts.show(request.part);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.n, request?.part]);

  const ordinary = !isResolutionLink(link.edge.type);
  const noun = eventsNoun(link.edge.type, link.source);
  const section = (part: LinkPart, title: string, content: React.ReactNode, onOpen?: () => void) => (
    <AccordionSection
      title={title}
      open={parts.isOpen(part)}
      onToggle={() => {
        if (!parts.isOpen(part)) onOpen?.();
        parts.toggle(part);
      }}
    >
      {content}
    </AccordionSection>
  );

  return (
    <>
      {section("details", "Details", <LinkDetails {...link} />)}
      {/* ADR-080: a link is changed with a reason and its history kept — in a case, for any type
          but the same-as ones, which are confirmed or marked as not the same. */}
      {assessment &&
        linkEditing &&
        link.source &&
        link.target &&
        ordinary &&
        section(
          "change",
          "Change this link",
          <LinkChange
            apiBaseUrl={assessment.apiBaseUrl}
            bearerToken={assessment.bearerToken}
            investigationId={assessment.investigationId}
            edge={link.edge}
            sourceType={link.source.type}
            targetType={link.target.type}
            edgeTypes={linkEditing.edgeTypes}
            openSignal={linkEditing.openChangeSignal + changeOpens}
            onChanged={linkEditing.onChanged}
            proposedTypes={linkEditing.proposedTypes}
            onTypeProposed={linkEditing.onTypeProposed}
          />,
          () => setChangeOpens((n) => n + 1),
        )}
      {/* ADR-075: notes belong to a case, so they are offered only where one is open. */}
      {assessment &&
        section(
          "notes",
          "Notes",
          <LinkNotes
            apiBaseUrl={assessment.apiBaseUrl}
            bearerToken={assessment.bearerToken}
            investigationId={assessment.investigationId}
            edgeId={link.edge.id}
            focusSignal={linkEditing?.openNoteSignal}
          />,
        )}
      {/* ADR-089: the events behind the link (the emails between two addresses). */}
      {assessment &&
        ordinary &&
        section(
          "events",
          nounWords(noun).title,
          <LinkEvents
            apiBaseUrl={assessment.apiBaseUrl}
            bearerToken={assessment.bearerToken}
            investigationId={assessment.investigationId}
            edgeId={link.edge.id}
            noun={noun}
            sourceLabel={link.source ? displayValue(link.source) : link.edge.source}
            targetLabel={link.target ? displayValue(link.target) : link.edge.target}
            focusSignal={linkEditing?.openEventsSignal}
            onDelta={linkEditing?.onDelta}
            onReadFullScreen={linkEditing?.onReadFullScreen}
            getEventsWindow={linkEditing?.getEventsWindow}
          />,
        )}
      {assessment &&
        ordinary &&
        section(
          "history",
          "Change history",
          <LinkHistory
            apiBaseUrl={assessment.apiBaseUrl}
            bearerToken={assessment.bearerToken}
            investigationId={assessment.investigationId}
            edgeId={link.edge.id}
          />,
        )}
    </>
  );
}

function NodeView({ node, assessment }: { node: Node | null; assessment: InspectorProps["assessment"] }) {
  const parts = useOpenParts<NodePart>(node ? ["properties"] : ["judgements"]);
  // Judgements fetches the case's whole list, so it is built the first time its part is opened
  // and kept from then on, not built hidden for every node selected.
  const [judgementsWanted, setJudgementsWanted] = useState(!node);
  const section = (part: NodePart, title: string, content: React.ReactNode) => (
    <AccordionSection
      title={title}
      open={parts.isOpen(part)}
      onToggle={() => {
        if (part === "judgements") setJudgementsWanted(true);
        parts.toggle(part);
      }}
    >
      {content}
    </AccordionSection>
  );
  return (
    <>
      {!node && <p style={{ color: "var(--text-tertiary)", margin: 0 }}>Select a node to inspect it.</p>}
      {node &&
        section(
          "properties",
          "Properties",
          <dl style={{ margin: 0 }}>
            <div>
              <dt style={{ color: "var(--text-secondary)" }}>Type</dt>
              <dd className="value">{node.type}</dd>
            </div>
            <div>
              <dt style={{ color: "var(--text-secondary)" }}>ID</dt>
              <dd className="identifier">{node.id}</dd>
            </div>
            {Object.entries(node.properties ?? {}).map(([key, value]) => (
              <div key={key}>
                <dt style={{ color: "var(--text-secondary)" }}>{key}</dt>
                <dd className="value">{String(value)}</dd>
              </div>
            ))}
          </dl>,
        )}
      {node &&
        section(
          "provenance",
          "Provenance",
          <div>
            <p style={{ margin: 0 }}>
              State: <span className="value">{node.provenance.state}</span>
            </p>
            <p style={{ margin: 0 }}>
              First seen: <span className="value">{node.provenance.first_seen}</span>
            </p>
          </div>,
        )}
      {node &&
        section(
          "source",
          "Source",
          <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
            {node.provenance.sources.map((source, i) => (
              <li key={i} className="value">
                {source.document_id} · {source.locator}
              </li>
            ))}
          </ul>,
        )}
      {assessment &&
        section(
          "judgements",
          "Judgements",
          judgementsWanted && (
          <JudgementsPanel
            apiBaseUrl={assessment.apiBaseUrl}
            bearerToken={assessment.bearerToken}
            investigationId={assessment.investigationId}
            workingSetGraph={assessment.workingSetGraph}
            selectedNodeId={node?.id ?? null}
            onHighlightNodes={assessment.onHighlightNodes}
            onJudgementsChange={assessment.onJudgementsChange}
          />
          ),
        )}
    </>
  );
}
