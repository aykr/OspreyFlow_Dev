import type Graph from "graphology";
import type { EdgeTypeDef, Judgement, Node } from "../../../../packages/schemas/generated";
import { JudgementsPanel } from "../assessment/JudgementsPanel";
import { Panel } from "../design/primitives/Panel";
import { AccordionSection } from "../design/primitives/AccordionSection";
import { EntityPicture, type EntityPictureProps } from "./EntityPicture";
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
import { linkTypeName } from "../canvas/linkLabel";
import type { EntityVisual } from "../ontology/schema";
import { SelectionList } from "./SelectionList";
import { onEntityPicturesChange } from "../canvas/entityPictures";
import { onIconChoicesChange, valueIconShownFor } from "../canvas/iconChoices";
import { describeIconForValue } from "../canvas/valueIcons";
import { TypeChip } from "./TypeChip";
import { NeighbourhoodRisk, type NeighbourhoodRiskProps } from "./NeighbourhoodRisk";
import { SharedContacts, type SharedContactsProps } from "./SharedContacts";
import { SOURCES_WITHHELD_TEXT } from "./sourcesWithheld";
import type { HandlingScheme } from "../ingest/api";

function isResolutionLink(type: string): boolean {
  return type === "SAME_AS" || type === "NOT_SAME_AS";
}

export interface InspectorProps {
  node: Node | null;
  /** Expand the node through the canvas's own preview, which counts in the store before anything is
   * drawn (ADR-115 E4). Absent: not offered. */
  onExpand?: (nodeId: string) => void;
  /** More than one node selected (ADR-097 step 1): the Inspector shows them together, not the
   * first alone. With fewer than two, the single node above is shown. */
  selection?: {
    nodes: readonly Node[];
    onCentre: (nodeId: string) => void;
    onRemove: (nodeId: string) => void;
  };
  /** How the canvas draws each entity type, for the type chip. Absent: the type is named only. */
  visualFor?: (entityType: string) => EntityVisual | undefined;
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
    /** The deployment's handling scheme, so a link's handling can be changed (ADR-102). */
    handlingScheme?: HandlingScheme;
  };
  /** ADR-100 Amendment 7: who shares contacts with the selected node. Absent: not offered. */
  sharedContacts?: Omit<SharedContactsProps, "node">;
  /** ADR-109 phase E: the selected entity's neighbourhood risk, on demand. Absent: not offered. */
  neighbourhoodRisk?: Omit<NeighbourhoodRiskProps, "node">;
  /** ADR-105: the entity's own picture. Absent: not offered. */
  picture?: EntityPictureProps;
  /** Rises when a node's menu chose *Set picture…* (ADR-105 Amendment 1): the Picture part opens.
   * The same rising-counter shape as the link menu's `open*Signal`s. */
  openPictureSignal?: number;
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
type NodePart = "properties" | "picture" | "relationships" | "shared" | "risk" | "provenance" | "source" | "judgements";

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
export function Inspector({
  node,
  onExpand,
  link,
  linkEditing,
  assessment,
  selection,
  visualFor,
  sharedContacts,
  neighbourhoodRisk,
  picture,
  openPictureSignal,
}: InspectorProps) {
  // The link menu's counters only ever rise; a part opens when one rises, never on a later
  // selection just because a counter is above zero.
  const seen = useRef({ note: 0, change: 0, events: 0, history: 0 });
  const [request, setRequest] = useState<PartRequest | null>(null);
  // A change of the analyst's icon choice or of an entity's own picture decides whether a value icon
  // is drawn, so the line naming it is worked out again.
  const [, setIconSeq] = useState(0);
  useEffect(() => {
    const again = () => setIconSeq((n) => n + 1);
    const offChoices = onIconChoicesChange(again);
    const offPictures = onEntityPicturesChange(again);
    return () => {
      offChoices();
      offPictures();
    };
  }, []);
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

  if (selection && selection.nodes.length >= 2) {
    return (
      <Panel title="Inspector" className="inspector">
        <SelectionView
          key={selection.nodes.map((n) => n.id).join("|")}
          selection={selection}
          graph={assessment?.workingSetGraph}
          visualFor={visualFor}
        />
      </Panel>
    );
  }

  if (!node && !assessment) {
    return (
      <Panel title="Inspector" className="inspector">
        <p style={{ color: "var(--text-tertiary)", margin: 0 }}>{EMPTY_STATE}</p>
      </Panel>
    );
  }

  return (
    <Panel title="Inspector" className="inspector">
      <NodeView
        key={node?.id ?? "no-node"}
        node={node}
        onExpand={onExpand}
        assessment={assessment}
        visualFor={visualFor}
        sharedContacts={sharedContacts}
        neighbourhoodRisk={neighbourhoodRisk}
        picture={picture}
        openPictureSignal={openPictureSignal}
      />
    </Panel>
  );
}

/** What the Inspector says with nothing selected: how to begin, with one action (review item 4). */
const EMPTY_STATE = "Select a node, or press / to search.";

/** The links of `nodeId` in view, by type, in display names, most first. */
function linksByType(graph: Graph | undefined, keep: (source: string, target: string) => boolean, edges: string[]) {
  const counts = new Map<string, number>();
  for (const key of edges) {
    const data = graph?.getEdgeAttribute(key, "data") as { type: string; source: string; target: string } | undefined;
    if (!data || !keep(data.source, data.target)) continue;
    counts.set(data.type, (counts.get(data.type) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function CountList({ rows }: { rows: [string, number][] }) {
  return (
    <ul role="list" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-2)" }}>
      {rows.map(([type, count]) => (
        <li key={type} style={{ display: "flex", justifyContent: "space-between", gap: "var(--sp-8)" }}>
          <span>{linkTypeName(type, [])}</span>
          <span className="value">{count}</span>
        </li>
      ))}
    </ul>
  );
}

function SelectionView({
  selection,
  graph,
  visualFor,
}: {
  selection: NonNullable<InspectorProps["selection"]>;
  graph: Graph | undefined;
  visualFor?: InspectorProps["visualFor"];
}) {
  type Part = "summary" | "selected" | "between";
  const parts = useOpenParts<Part>(["summary"]);
  const nodes = selection.nodes;
  const ids = new Set(nodes.map((n) => n.id));
  const byType = new Map<string, number>();
  for (const n of nodes) byType.set(n.type, (byType.get(n.type) ?? 0) + 1);
  // Properties every selected node has, with one value among them.
  const shared = Object.entries(nodes[0]?.properties ?? {}).filter(([key, value]) =>
    nodes.every((n) => n.properties?.[key] !== undefined && String(n.properties[key]) === String(value)),
  );
  const between = graph
    ? linksByType(graph, (s, t) => ids.has(s) && ids.has(t), graph.edges().filter((k) => {
        const [s, t] = graph.extremities(k);
        return ids.has(s) && ids.has(t);
      }))
    : [];
  const betweenCount = between.reduce((sum, [, n]) => sum + n, 0);
  const section = (part: Part, title: string, content: React.ReactNode) => (
    <AccordionSection title={title} open={parts.isOpen(part)} onToggle={() => parts.toggle(part)}>
      {content}
    </AccordionSection>
  );
  return (
    <>
      {section(
        "summary",
        "Summary",
        <div style={{ display: "grid", gap: "var(--sp-8)" }}>
          <ul role="list" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-2)" }}>
            {[...byType.entries()].map(([type, count]) => (
              <li key={type} style={{ display: "flex", alignItems: "center", gap: "var(--sp-6)" }}>
                <TypeChip type={`${count} ${type}`} visual={visualFor?.(type)} />
              </li>
            ))}
          </ul>
          {shared.length > 0 ? (
            <dl style={{ margin: 0 }}>
              {shared.map(([key, value]) => (
                <div key={key}>
                  <dt style={{ color: "var(--text-secondary)" }}>{key}, shared</dt>
                  <dd className="value">{String(value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p style={{ margin: 0, color: "var(--text-tertiary)" }}>No property has one value across them all.</p>
          )}
        </div>,
      )}
      {section(
        "selected",
        // ADR-115 E4 (review item 2): the selection bar holds the one count.
        "Selected",
        <SelectionList nodes={nodes} onCentre={selection.onCentre} onRemove={selection.onRemove} />,
      )}
      {section(
        "between",
        `Links between them (${betweenCount})`,
        between.length > 0 ? (
          <CountList rows={between} />
        ) : (
          <p style={{ margin: 0, color: "var(--text-tertiary)" }}>No link joins two of them in this view.</p>
        ),
      )}
    </>
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
            handlingScheme={linkEditing.handlingScheme}
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

function NodeView({
  node,
  onExpand,
  assessment,
  visualFor,
  sharedContacts,
  neighbourhoodRisk,
  picture,
  openPictureSignal,
}: {
  node: Node | null;
  onExpand?: InspectorProps["onExpand"];
  assessment: InspectorProps["assessment"];
  visualFor?: InspectorProps["visualFor"];
  sharedContacts?: InspectorProps["sharedContacts"];
  neighbourhoodRisk?: InspectorProps["neighbourhoodRisk"];
  picture?: InspectorProps["picture"];
  openPictureSignal?: number;
}) {
  const parts = useOpenParts<NodePart>(node ? ["properties"] : ["judgements"]);
  // *Set picture…* on the node's menu (ADR-105 Amendment 1): the Picture part opens when the
  // signal rises, never merely because it is above zero on a later selection.
  const pictureSignalSeen = useRef(openPictureSignal ?? 0);
  useEffect(() => {
    if ((openPictureSignal ?? 0) > pictureSignalSeen.current) {
      pictureSignalSeen.current = openPictureSignal ?? 0;
      parts.show("picture");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openPictureSignal]);
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
      {!node && <p style={{ color: "var(--text-tertiary)", margin: 0 }}>{EMPTY_STATE}</p>}
      {node && (
        // The node as the canvas draws it, then its name as a literal value (review item 4).
        <h3 style={{ margin: "0 0 var(--sp-8)", display: "flex", alignItems: "center", gap: "var(--sp-8)", fontSize: "var(--fs-13)" }}>
          <TypeChip type={node.type} visual={visualFor?.(node.type)} />
          <span className="value" style={{ fontWeight: 400, overflowWrap: "anywhere" }}>
            {displayValue(node)}
          </span>
          {/* ADR-115 E4: the node's own marking beside its type (the reference's badge). */}
          {node.handling?.classification && (
            <span aria-label="Marking" className="value marking-badge">
              {node.handling.classification}
            </span>
          )}
        </h3>
      )}
      {node &&
        section(
          "properties",
          "Properties",
          <dl className="inspector-keys">
            <div>
              <dt style={{ color: "var(--text-secondary)" }}>Type</dt>
              <dd className="value">{node.type}</dd>
            </div>
            <div>
              <dt style={{ color: "var(--text-secondary)" }}>ID</dt>
              <dd className="identifier">{node.id}</dd>
            </div>
            {(() => {
              // ADR-128 Decision 4: which icon this node's value stands for, when its type maps one.
              // Only when the renderer draws it: the node's own picture and the analyst's choice for
              // the type come first (`valueIconShownFor`, shared with the legend).
              const rule = visualFor?.(node.type)?.iconByValue;
              const given = valueIconShownFor(node.id, node.type, rule, node.properties);
              if (!rule || !given) return null;
              return (
                <div>
                  <dt style={{ color: "var(--text-secondary)" }}>Icon for this value</dt>
                  <dd className="value">{describeIconForValue(rule.property, given)}</dd>
                </div>
              );
            })()}
            {Object.entries(node.properties ?? {}).map(([key, value]) => (
              <div key={key}>
                <dt style={{ color: "var(--text-secondary)" }}>{key}</dt>
                <dd className="value">{String(value)}</dd>
              </div>
            ))}
          </dl>,
        )}
      {node &&
        picture?.types.has(node.type) &&
        section("picture", "Picture", <EntityPicture {...picture} nodeId={node.id} />)}
      {node &&
        section(
          "relationships",
          "Relationships",
          (() => {
            const graph = assessment?.workingSetGraph;
            const rows = graph?.hasNode(node.id)
              ? linksByType(graph, () => true, graph.edges(node.id))
              : [];
            return (
              <div style={{ display: "grid", gap: "var(--sp-8)" }}>
                {rows.length > 0 ? (
                  <CountList rows={rows} />
                ) : (
                  <p style={{ margin: 0, color: "var(--text-tertiary)" }}>No links in this view.</p>
                )}
                {onExpand && (
                  <>
                    <p style={{ margin: 0, color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
                      Drawn in this view. Expand counts the rest in the store before anything is drawn.
                    </p>
                    <button type="button" className="btn" style={{ justifySelf: "start" }}
                            aria-label={`Expand ${displayValue(node)}`} onClick={() => onExpand(node.id)}>
                      Expand
                    </button>
                  </>
                )}
              </div>
            );
          })(),
        )}
      {node &&
        sharedContacts &&
        section("shared", "Shares contacts", <SharedContacts {...sharedContacts} node={node} />)}
      {node &&
        neighbourhoodRisk &&
        section("risk", "Neighbourhood risk", <NeighbourhoodRisk {...neighbourhoodRisk} node={node} />)}
      {node &&
        section(
          "provenance",
          "Provenance",
          <div>
            <p style={{ margin: 0, display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
              {/* ADR-115 E4: the stroke the canvas draws this provenance with (DESIGN.md §3.8). */}
              <svg className="provenance-stroke" width="22" height="8" aria-hidden="true">
                <line x1="1" y1="4" x2="21" y2="4"
                      strokeDasharray={node.provenance.state === "asserted" ? undefined : node.provenance.state === "inferred" ? "4 3" : "1 3"} />
              </svg>
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
          node.provenance.sources_withheld ? (
            <p style={{ margin: 0, color: "var(--text-secondary)" }}>{SOURCES_WITHHELD_TEXT}</p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
              {node.provenance.sources.map((source, i) => (
                <li key={i} className="value">
                  {source.document_id} · {source.locator}
                </li>
              ))}
            </ul>
          ),
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
