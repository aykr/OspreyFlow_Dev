// Where an analyst new to a case's data starts (ADR-100): what the data holds, its most connected
// nodes, and each entity type's most connected. Every figure is the Conduit's, computed in the
// store within the case's datasets and the analyst's clearance; this panel adds nothing up itself.
// A ranking says of how many and pages rather than stops (rule 2), and every item puts its node on
// the canvas with one action, as choosing a search result does.
import { useEffect, useState } from "react";

import type { Node } from "../../../../packages/schemas/generated";
import { nodeLabel } from "../canvas/nodeAttributes";
import { linkCaption, linkTypeName, type NamedType } from "../canvas/linkLabel";
import { eventsNoun } from "../inspector/linkEventsApi";
import {
  loadBusiestDays,
  loadBusiestLinks,
  loadGroups,
  type Groups,
  loadMostConnected,
  loadTypeCounts,
  loadWhatsNew,
  type BusyDay,
  type LoadSummary,
  type WhatsNew,
  type RankedLink,
  type RankedNode,
  type TypeCounts,
} from "./exploreApi";

/** How many the overall ranking shows first, and how many each type shows when opened. */
export const TOP = 10;
export const TOP_PER_TYPE = 5;
/** How many more one "Show more" asks for. */
export const PAGE = 10;

const COUNT = new Intl.NumberFormat("en-GB");
const AT = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });

export interface ExplorePanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The ontology's link types, for their names. */
  edgeTypes: readonly NamedType[];
  /** Puts the node on the canvas. */
  onPick: (node: Node) => void;
  /** Puts a link and both its ends on the canvas. */
  onPickLink?: (link: RankedLink) => void;
  /** Sets the timeline's window to the day. */
  onPickDay?: (day: BusyDay) => void;
}

const WHEN = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

function when(iso: string): string {
  return `${WHEN.format(new Date(iso))} UTC`;
}

const DAY = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

function byCount(counts: Record<string, number>): [string, number][] {
  return Object.entries(counts)
    .filter(([, n]) => n > 0)
    .sort(([a, x], [b, y]) => y - x || a.localeCompare(b));
}

function plural(n: number, one: string, many: string): string {
  return `${COUNT.format(n)} ${n === 1 ? one : many}`;
}

/** One page of something ranked, as the Conduit answers it. */
interface Page<T> {
  items: T[];
  total: number;
}

interface PagedProps<T> {
  /** Asks the Conduit for one page. */
  load: (offset: number, limit: number) => Promise<Page<T>>;
  /** Changes when what is ranked changes (another case, another type), starting it again. */
  resetKey: string;
  first: number;
  /** "most connected", "busiest": what the caption says the list is. */
  what: string;
  keyOf: (item: T) => string;
  labelOf: (item: T) => string;
  onPick: (item: T) => void;
}

/** A ranking: its first page, then more on request, always saying of how many (rule 2). */
function Paged<T>({ load, resetKey, first, what, keyOf, labelOf, onPick }: PagedProps<T>) {
  const [rows, setRows] = useState<T[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function page(offset: number, limit: number) {
    setLoading(true);
    try {
      const answer = await load(offset, limit);
      setRows((shown) => [...shown.slice(0, offset), ...answer.items]);
      setTotal(answer.total);
      setProblem(null);
    } catch (err: unknown) {
      setProblem(err instanceof Error ? err.message : "This could not be read.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setRows([]);
    setTotal(null);
    void page(0, first);
    // A new case or type starts the ranking again; `load` is rebuilt every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey, first]);

  if (problem) return <p role="alert">{problem}</p>;
  if (total === null) return <p style={{ color: "var(--text-tertiary)" }}>Counting…</p>;
  if (total === 0) return <p style={{ color: "var(--text-tertiary)", margin: 0 }}>None you can see.</p>;
  const more = Math.min(PAGE, total - rows.length);
  return (
    <div style={{ display: "grid", gap: "var(--sp-4)" }}>
      <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
        {rows.length < total
          ? `The ${COUNT.format(rows.length)} ${what} of ${COUNT.format(total)}.`
          : `All ${COUNT.format(total)} shown.`}
      </p>
      <ol style={{ margin: 0, paddingLeft: "var(--sp-16)", display: "grid", gap: "var(--sp-4)" }}>
        {rows.map((item) => (
          <li key={keyOf(item)}>
            <button type="button" className="btn btn--quiet" onClick={() => onPick(item)}>
              {labelOf(item)}
            </button>
          </li>
        ))}
      </ol>
      {more > 0 && (
        <button
          type="button"
          className="btn btn--quiet"
          disabled={loading}
          onClick={() => void page(rows.length, more)}
        >
          {`Show ${COUNT.format(more)} more`}
        </button>
      )}
    </div>
  );
}

interface RankingProps extends Omit<ExplorePanelProps, "edgeTypes" | "onPickLink" | "onPickDay"> {
  entityType?: string;
  first: number;
}

/** Nodes by degree, of one type when named. */
function Ranking({ apiBaseUrl, bearerToken, investigationId, entityType, first, onPick }: RankingProps) {
  return (
    <Paged<RankedNode>
      load={async (offset, limit) => {
        const answer = await loadMostConnected(apiBaseUrl, bearerToken, investigationId, {
          entityType,
          limit,
          offset,
        });
        return { items: answer.nodes, total: answer.total };
      }}
      resetKey={`${apiBaseUrl}|${investigationId}|${entityType ?? ""}`}
      first={first}
      what="most connected"
      keyOf={({ node }) => node.id}
      labelOf={({ node, degree }) => `${nodeLabel(node)} · ${node.type} · ${plural(degree, "link", "links")}`}
      onPick={({ node }) => onPick(node)}
    />
  );
}

function TypeEntry({ name, count, ...ranking }: Omit<RankingProps, "first" | "entityType"> & { name: string; count: number }) {
  const [open, setOpen] = useState(false);
  return (
    <li>
      <button type="button" className="btn btn--quiet" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {`${name} · ${COUNT.format(count)}`}
      </button>
      {open && <Ranking {...ranking} entityType={name} first={TOP_PER_TYPE} />}
    </li>
  );
}

/** The case's largest groups and the nodes bridging them (ADR-100 decision 6), read once. */
function GroupsAndBridges({ apiBaseUrl, bearerToken, investigationId, onPick }: Omit<ExplorePanelProps, "edgeTypes">) {
  const [found, setFound] = useState<Groups | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setFound(null);
    setProblem(null);
    loadGroups(apiBaseUrl, bearerToken, investigationId)
      .then((answer) => !cancelled && setFound(answer))
      .catch((err: unknown) => {
        if (!cancelled) setProblem(err instanceof Error ? err.message : "The groups could not be read.");
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);
  if (problem) return <p role="alert">{problem}</p>;
  if (!found) return <p style={{ color: "var(--text-tertiary)" }}>Finding groups…</p>;
  const caption = { color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 };
  const list = { margin: 0, paddingLeft: "var(--sp-16)", display: "grid", gap: "var(--sp-4)" };
  return (
    <div style={{ display: "grid", gap: "var(--sp-8)" }}>
      <p style={caption}>
        {`The largest ${COUNT.format(found.groups.length)} of ${COUNT.format(found.total_groups)} groups` +
          (found.not_shown_groups > 0 ? `; ${COUNT.format(found.not_shown_groups)} not shown.` : ".")}
      </p>
      <ol style={list}>
        {found.groups.map((group) => (
          <li key={group.id}>
            <button type="button" className="btn btn--quiet" onClick={() => onPick(group.central)}>
              {`Group of ${COUNT.format(group.size)} · mostly ${group.dominant_type} · around ${nodeLabel(group.central)}`}
            </button>
          </li>
        ))}
      </ol>
      {found.total_bridges > 0 && (
        <>
          <p style={caption}>
            {`The strongest ${COUNT.format(found.bridges.length)} of ${COUNT.format(found.total_bridges)} bridges.`}
          </p>
          <ol style={list}>
            {found.bridges.map((bridge) => (
              <li key={bridge.node.id}>
                <button type="button" className="btn btn--quiet" onClick={() => onPick(bridge.node)}>
                  {`${nodeLabel(bridge.node)} · reaches ${plural(bridge.groups_reached, "other group", "other groups")} · ${plural(bridge.links, "link", "links")}`}
                </button>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

function loadLabel(load: LoadSummary): string {
  const recipe = load.recipe_id
    ? ` · ${load.recipe_id}${load.recipe_version != null ? ` v${load.recipe_version}` : ""}`
    : "";
  return (
    `${load.load_id ?? "Written outside a load"}${recipe} · ` +
    `${plural(load.nodes, "entity", "entities")} and ${plural(load.links, "link", "links")} · ` +
    `latest ${when(load.latest)}`
  );
}

/** "The latest 10 of 14 loads." or "All 3 confirmed shown.", or `none` when there are none. */
function Shown({ shown, total, what, none }: { shown: number; total: number; what: string; none: string }) {
  const caption = { color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 };
  if (total === 0) return <p style={caption}>{none}</p>;
  return (
    <p style={caption}>
      {shown < total
        ? `The latest ${COUNT.format(shown)} of ${COUNT.format(total)} ${what}.`
        : `All ${COUNT.format(total)} ${what} shown.`}
    </p>
  );
}

/** ADR-100 decision 7 (Amendment 6): the latest loads, and the nodes colleagues confirmed or
 * marked, read once per opening. A load is named, not picked: it can hold the whole case. */
function WhatIsNew({ apiBaseUrl, bearerToken, investigationId, onPick }: Omit<ExplorePanelProps, "edgeTypes">) {
  const [news, setNews] = useState<WhatsNew | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setNews(null);
    setProblem(null);
    loadWhatsNew(apiBaseUrl, bearerToken, investigationId)
      .then((answer) => !cancelled && setNews(answer))
      .catch((err: unknown) => {
        if (!cancelled) setProblem(err instanceof Error ? err.message : "What is new could not be read.");
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);
  if (problem) return <p role="alert">{problem}</p>;
  if (!news) return <p style={{ color: "var(--text-tertiary)" }}>Looking…</p>;
  const loads = news.loads ?? [];
  const confirmed = news.confirmed ?? [];
  const marked = news.marked ?? [];
  const list = { margin: 0, paddingLeft: "var(--sp-16)", display: "grid", gap: "var(--sp-4)" };
  return (
    <div style={{ display: "grid", gap: "var(--sp-8)" }}>
      <Shown shown={loads.length} total={news.loads_total ?? 0} what="loads" none="No loads you can see." />
      {loads.length > 0 && (
        <ol aria-label="Latest loads" style={{ ...list, fontSize: "var(--fs-12)" }}>
          {loads.map((load) => (
            <li key={load.load_id ?? ""}>{loadLabel(load)}</li>
          ))}
        </ol>
      )}
      <Shown
        shown={confirmed.length}
        total={news.confirmed_total ?? 0}
        what="confirmed"
        none="Nothing confirmed you can see."
      />
      {confirmed.length > 0 && (
        <ol aria-label="Recently confirmed" style={list}>
          {confirmed.map((c) => (
            <li key={c.node.id}>
              <button type="button" className="btn btn--quiet" onClick={() => onPick(c.node)}>
                {`${nodeLabel(c.node)} · ${c.node.type} · confirmed by ${c.confirmed_by} · ${when(c.confirmed_at)}`}
              </button>
            </li>
          ))}
        </ol>
      )}
      <Shown shown={marked.length} total={news.marked_total ?? 0} what="marked" none="Nothing marked you can see." />
      {marked.length > 0 && (
        <ol aria-label="Recently marked" style={list}>
          {marked.map((m) => (
            <li key={m.node.id}>
              <button type="button" className="btn btn--quiet" onClick={() => onPick(m.node)}>
                {`${nodeLabel(m.node)} · ${m.node.type} · marked for suppression by ${m.marked_by} · ${when(m.marked_at)} · “${m.reason}”`}
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function ExplorePanel(props: ExplorePanelProps) {
  const { apiBaseUrl, bearerToken, investigationId, edgeTypes } = props;
  const [counts, setCounts] = useState<TypeCounts | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setCounts(null);
    setProblem(null);
    loadTypeCounts(apiBaseUrl, bearerToken, investigationId)
      .then((found) => !cancelled && setCounts(found))
      .catch((err: unknown) => {
        if (!cancelled) setProblem(err instanceof Error ? err.message : "What this case holds could not be read.");
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);

  const ranking = {
    apiBaseUrl,
    bearerToken,
    investigationId,
    onPick: props.onPick,
  };
  const entities = counts ? byCount(counts.nodes ?? {}) : [];
  const links = counts ? byCount(counts.edges ?? {}) : [];
  const entityTotal = entities.reduce((sum, [, n]) => sum + n, 0);
  const linkTotal = links.reduce((sum, [, n]) => sum + n, 0);
  const heading = { fontSize: "var(--fs-13)", margin: "0 0 var(--sp-4)" };

  return (
    <div style={{ display: "grid", gap: "var(--sp-16)" }}>
      <section aria-labelledby="explore-holds">
        <h3 id="explore-holds" style={heading}>What this case holds</h3>
        {problem && <p role="alert">{problem}</p>}
        {!problem && counts === null && <p style={{ color: "var(--text-tertiary)" }}>Counting…</p>}
        {counts && entities.length === 0 && links.length === 0 && (
          <p>This case&apos;s data holds nothing you can see yet.</p>
        )}
        {counts && (entities.length > 0 || links.length > 0) && (
          <>
            <p style={{ color: "var(--text-secondary)", margin: "0 0 var(--sp-4)" }}>
              {`${plural(entityTotal, "entity", "entities")} and ${plural(linkTotal, "link", "links")}`}
            </p>
            {counts.computed_at && (
              // ADR-100 Amendment 3: the figures are kept, so they say when they were counted.
              <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: "0 0 var(--sp-4)" }}>
                {`Counted at ${AT.format(new Date(counts.computed_at))} UTC, and again after any change.`}
              </p>
            )}
            <ul style={{ margin: 0, paddingLeft: "var(--sp-16)", fontSize: "var(--fs-12)" }}>
              {entities.map(([name, n]) => (
                <li key={`n:${name}`}>{`${name} · ${COUNT.format(n)}`}</li>
              ))}
              {links.map(([name, n]) => (
                <li key={`e:${name}`}>{`${linkTypeName(name, edgeTypes)} · ${COUNT.format(n)}`}</li>
              ))}
            </ul>
          </>
        )}
      </section>
      {counts && entities.length > 0 && (
        <>
          <section aria-labelledby="explore-top">
            <h3 id="explore-top" style={heading}>Most connected</h3>
            <Ranking {...ranking} first={TOP} />
          </section>
          <section aria-labelledby="explore-types">
            <h3 id="explore-types" style={heading}>By entity type</h3>
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: "var(--sp-4)" }}>
              {entities.map(([name, n]) => (
                <TypeEntry key={name} {...ranking} name={name} count={n} />
              ))}
            </ul>
          </section>
          {links.length > 0 && (
            <section aria-labelledby="explore-links">
              <h3 id="explore-links" style={heading}>Busiest links</h3>
              <Paged<RankedLink>
                load={async (offset, limit) => {
                  const answer = await loadBusiestLinks(apiBaseUrl, bearerToken, investigationId, { limit, offset });
                  return { items: answer.links, total: answer.total };
                }}
                resetKey={`${apiBaseUrl}|${investigationId}`}
                first={TOP}
                what="busiest"
                keyOf={({ edge }) => edge.id}
                labelOf={({ edge, source, target }) =>
                  `${nodeLabel(source)} → ${nodeLabel(target)} · ${linkCaption(
                    linkTypeName(edge.type, edgeTypes),
                    edge.occurrences ?? 1,
                    eventsNoun(edge.type, source),
                  )}`
                }
                onPick={(link) => props.onPickLink?.(link)}
              />
            </section>
          )}
          {links.length > 0 && (
            <section aria-labelledby="explore-groups">
              <h3 id="explore-groups" style={heading}>Groups and bridges</h3>
              <GroupsAndBridges {...ranking} />
            </section>
          )}
          <section aria-labelledby="explore-new">
            <h3 id="explore-new" style={heading}>What&apos;s new</h3>
            <WhatIsNew {...ranking} />
          </section>
          <section aria-labelledby="explore-days">
            <h3 id="explore-days" style={heading}>Busiest days</h3>
            <Paged<BusyDay>
              load={async (offset, limit) => {
                const answer = await loadBusiestDays(apiBaseUrl, bearerToken, investigationId, { limit, offset });
                return { items: answer.days, total: answer.total };
              }}
              resetKey={`${apiBaseUrl}|${investigationId}`}
              first={TOP}
              what="busiest"
              keyOf={(day) => day.start}
              labelOf={(day) => `${DAY.format(new Date(day.start)).replace(",", "")} · ${plural(day.count, "event", "events")}`}
              onPick={(day) => props.onPickDay?.(day)}
            />
          </section>
        </>
      )}
    </div>
  );
}
