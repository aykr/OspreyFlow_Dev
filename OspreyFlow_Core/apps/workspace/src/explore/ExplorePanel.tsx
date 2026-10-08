// Where an analyst new to a case's data starts (ADR-100): what the data holds, its most connected
// nodes, and each entity type's most connected. Every figure is the Conduit's, computed in the
// store within the case's datasets and the analyst's clearance; this panel adds nothing up itself.
// A ranking says of how many and pages rather than stops (rule 2), and every item puts its node on
// the canvas with one action, as choosing a search result does.
import { useEffect, useState } from "react";

import type { Node } from "../../../../packages/schemas/generated";
import { nodeLabel } from "../canvas/nodeAttributes";
import { linkTypeName, type NamedType } from "../canvas/linkLabel";
import { loadMostConnected, loadTypeCounts, type RankedNode, type TypeCounts } from "./exploreApi";

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
}

function byCount(counts: Record<string, number>): [string, number][] {
  return Object.entries(counts)
    .filter(([, n]) => n > 0)
    .sort(([a, x], [b, y]) => y - x || a.localeCompare(b));
}

function plural(n: number, one: string, many: string): string {
  return `${COUNT.format(n)} ${n === 1 ? one : many}`;
}

interface RankingProps extends Omit<ExplorePanelProps, "edgeTypes"> {
  entityType?: string;
  first: number;
}

/** One ranking: its first page, then more on request, always saying of how many. */
function Ranking({ apiBaseUrl, bearerToken, investigationId, entityType, first, onPick }: RankingProps) {
  const [rows, setRows] = useState<RankedNode[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function load(offset: number, limit: number) {
    setLoading(true);
    try {
      const page = await loadMostConnected(apiBaseUrl, bearerToken, investigationId, {
        entityType,
        limit,
        offset,
      });
      setRows((shown) => [...shown.slice(0, offset), ...page.nodes]);
      setTotal(page.total);
      setProblem(null);
    } catch (err: unknown) {
      setProblem(err instanceof Error ? err.message : "The most connected could not be read.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setRows([]);
    setTotal(null);
    void load(0, first);
    // A new case or type starts the ranking again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl, bearerToken, investigationId, entityType, first]);

  if (problem) return <p role="alert">{problem}</p>;
  if (total === null) return <p style={{ color: "var(--text-tertiary)" }}>Counting…</p>;
  const more = Math.min(PAGE, total - rows.length);
  return (
    <div style={{ display: "grid", gap: "var(--sp-4)" }}>
      <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
        {rows.length < total
          ? `The ${COUNT.format(rows.length)} most connected of ${COUNT.format(total)}.`
          : `All ${COUNT.format(total)} shown.`}
      </p>
      <ol style={{ margin: 0, paddingLeft: "var(--sp-16)", display: "grid", gap: "var(--sp-4)" }}>
        {rows.map(({ node, degree }) => (
          <li key={node.id}>
            <button type="button" className="btn btn--quiet" onClick={() => onPick(node)}>
              {`${nodeLabel(node)} · ${node.type} · ${plural(degree, "link", "links")}`}
            </button>
          </li>
        ))}
      </ol>
      {more > 0 && (
        <button
          type="button"
          className="btn btn--quiet"
          disabled={loading}
          onClick={() => void load(rows.length, more)}
        >
          {`Show ${COUNT.format(more)} more`}
        </button>
      )}
    </div>
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
        </>
      )}
    </div>
  );
}
