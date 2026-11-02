// The Matrix view — `02_GLASS_FRONTEND.md` §6: "the Matrix view is not a novelty, it is the
// screen-reader-navigable rendering of the same data"; §2 rule 1: "Graph, Map and Matrix are three
// renderings of the same graphology instance. Switching view never refetches and never loses
// selection." GDS remediation plan item A1.
//
// Two real HTML tables, entities and links, over the working set's own graph (`matrixRows.ts`): a
// caption naming each and saying how it is sorted and which rows are shown, a column header per
// column, the name as each row's header. Each table is an ARIA grid: one Tab stop, the arrow keys
// between cells, Home and End along a row, Ctrl+Home and Ctrl+End to the corners, Page Down and
// Page Up between pages. Enter selects the row's node (as a click does on the canvas), Space adds
// it to or takes it out of the selection (as Space does on the canvas), and the selection is the
// one the caller holds for the canvas and the Inspector: this view keeps none of its own.
//
// A long view is paged (rule 2: the caption says "Rows 101 to 200 of 12,481", never a silent cut);
// a page is a hundred rows, so a page draws well inside §5's budget at 50,000 nodes and every row
// on it is in the page for a screen reader to find — a virtualised table would hide rows from one.
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useStore } from "zustand/react";
import type { StoreApi } from "zustand/vanilla";

import type { NamedType } from "../canvas/linkLabel";
import { TypeChip } from "../inspector/TypeChip";
import type { EntityVisual } from "../ontology/schema";
import type { WorkingSetGraph, WorkingSetStoreState } from "../workingset/store";
import { fetchConnectionStrengths, fetchRarity } from "../strength/api";
import {
  entityRows,
  linkRows,
  pageContaining,
  pageOf,
  provenanceText,
  sortRows,
  type EntityRow,
  type LinkRow,
  type LinkValues,
  type SortDirection,
} from "./matrixRows";

export interface MatrixViewProps {
  graph: WorkingSetGraph;
  store: StoreApi<WorkingSetStoreState>;
  edgeTypes: readonly NamedType[];
  visualFor?: (type: string) => EntityVisual | undefined;
  /** What the cross-filter dims on the canvas: kept here, and said to be dimmed (§2 rule 2). */
  dimmedNodeIds?: ReadonlySet<string>;
  dimmedEdgeIds?: ReadonlySet<string>;
  /** The selection the canvas and the Inspector use. */
  selectedNodeIds: readonly string[];
  selectedEdgeId: string | null;
  onSelectNodes: (nodeIds: string[]) => void;
  onSelectLink: (edgeId: string | null) => void;
  /** The canvas's own Expand, through its preview and the working set's cap (rule 2). */
  onExpand: (nodeId: string) => void;
  onShowOnGraph: (nodeId: string) => void;
  /** ADR-139 decision 6: where to work out each link's connection strength and the rarity of its two
   * ends, so the link table sorts by both. Absent, neither column is shown. */
  strength?: { apiBaseUrl: string; bearerToken: string; investigationId: string };
}

const COUNT = new Intl.NumberFormat("en-GB");
const STRENGTH = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const NONE: ReadonlySet<string> = new Set();

interface Column<R> {
  key: string;
  header: string;
  /** The row field this column sorts by; absent, the column does not sort. */
  sortBy?: keyof R & string;
  numeric?: boolean;
  /** The row's header: its name. One per table. */
  rowHeader?: boolean;
  render?: (row: R) => ReactNode;
  /** A button in the cell, rather than a value. */
  action?: { text: string; name: (row: R) => string; run: (row: R) => void };
}

interface GridProps<R extends { id: string; dimmed: boolean }> {
  noun: "entities" | "links";
  rows: R[];
  columns: Column<R>[];
  defaultSort: keyof R & string;
  multiselectable: boolean;
  isSelected: (row: R) => boolean;
  /** `toggle`: Space or Ctrl+click, adding to or taking out of the selection. */
  onSelect: (row: R, toggle: boolean) => void;
  /** The page to open on: the one holding the first selected row. */
  openOn: string | null;
  describedBy: string;
}

function sortWords(column: Column<unknown>, direction: SortDirection): string {
  if (column.numeric) return direction === "ascending" ? "fewest first" : "most first";
  return direction === "ascending" ? "A to Z" : "Z to A";
}

function SortMark({ direction }: { direction: SortDirection }) {
  return (
    <svg aria-hidden="true" width="8" height="8" viewBox="0 0 8 8" className="matrix-grid__sort-mark">
      <path d={direction === "ascending" ? "M4 1 L7 6 L1 6 Z" : "M1 2 L7 2 L4 7 Z"} />
    </svg>
  );
}

function Grid<R extends { id: string; dimmed: boolean }>({
  noun,
  rows,
  columns,
  defaultSort,
  multiselectable,
  isSelected,
  onSelect,
  openOn,
  describedBy,
}: GridProps<R>) {
  const [sort, setSort] = useState<{ key: keyof R & string; direction: SortDirection }>({
    key: defaultSort,
    direction: "ascending",
  });
  const sorted = useMemo(() => sortRows(rows, sort.key, sort.direction), [rows, sort]);
  // Opens on the page holding the selection made on the canvas, so it is in view.
  const [page, setPage] = useState<number>(() => (openOn ? (pageContaining(sorted, openOn) ?? 0) : 0));
  const shown = pageOf(sorted, page);
  const [active, setActive] = useState<{ row: number; col: number }>(() => {
    const at = openOn ? shown.rows.findIndex((r) => r.id === openOn) : -1;
    return at >= 0 ? { row: at + 1, col: 0 } : { row: 0, col: 0 };
  });
  // Rows can leave (the working set changed, the page turned): the active cell stays on the grid.
  const row = Math.min(active.row, shown.rows.length);
  const col = Math.min(active.col, columns.length - 1);
  const tableRef = useRef<HTMLTableElement>(null);
  const moveFocus = useRef(false);

  useLayoutEffect(() => {
    if (!moveFocus.current) return;
    moveFocus.current = false;
    tableRef.current?.querySelector<HTMLElement>(`[data-cell="${row}:${col}"]`)?.focus();
  });

  const go = (to: { row: number; col: number }) => {
    moveFocus.current = true;
    setActive({
      row: Math.max(0, Math.min(to.row, shown.rows.length)),
      col: Math.max(0, Math.min(to.col, columns.length - 1)),
    });
  };
  const turn = (to: number) => {
    const next = Math.max(0, Math.min(to, shown.pages - 1));
    if (next === shown.page) return;
    moveFocus.current = true;
    setPage(next);
  };

  const sortColumn = sort.key;
  const onSortBy = (column: Column<R>) => {
    const key = column.sortBy!;
    setSort((now) =>
      now.key === key
        ? { key, direction: now.direction === "ascending" ? "descending" : "ascending" }
        : { key, direction: column.numeric ? "descending" : "ascending" },
    );
    setPage(0);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTableElement>) => {
    const onButton = (e.target as HTMLElement).tagName === "BUTTON";
    const ctrl = e.ctrlKey || e.metaKey;
    switch (e.key) {
      case "ArrowDown":
        go({ row: row + 1, col });
        break;
      case "ArrowUp":
        go({ row: row - 1, col });
        break;
      case "ArrowRight":
        go({ row, col: col + 1 });
        break;
      case "ArrowLeft":
        go({ row, col: col - 1 });
        break;
      case "Home":
        go(ctrl ? { row: 0, col: 0 } : { row, col: 0 });
        break;
      case "End":
        go(ctrl ? { row: shown.rows.length, col: columns.length - 1 } : { row, col: columns.length - 1 });
        break;
      case "PageDown":
        turn(shown.page + 1);
        break;
      case "PageUp":
        turn(shown.page - 1);
        break;
      case "Enter":
      case " ": {
        // A button in the grid (a sort, Expand, Show) does its own thing.
        if (onButton || row === 0) return;
        const target = shown.rows[row - 1];
        if (target) onSelect(target, e.key === " ");
        break;
      }
      default:
        return;
    }
    e.preventDefault();
  };

  const sortedBy = columns.find((c) => c.sortBy === sortColumn) ?? columns[0]!;
  const title = noun === "entities" ? "Entities" : "Links";
  const caption =
    `${title} in this view, ${COUNT.format(shown.total)}. ` +
    `Sorted by ${sortedBy.header.toLowerCase()}, ${sortWords(sortedBy as Column<unknown>, sort.direction)}. ` +
    `Rows ${COUNT.format(shown.first)} to ${COUNT.format(shown.last)} of ${COUNT.format(shown.total)}.`;

  const tab = (r: number, c: number) => (r === row && c === col ? 0 : -1);

  return (
    <>
      <table
        ref={tableRef}
        role="grid"
        className="table matrix-grid"
        aria-multiselectable={multiselectable}
        aria-rowcount={shown.total + 1}
        aria-describedby={describedBy}
        onKeyDown={onKeyDown}
        onFocus={(e) => {
          const cell = (e.target as HTMLElement).closest<HTMLElement>("[data-cell]");
          const [r, c] = (cell?.dataset.cell ?? "").split(":").map(Number);
          if (r !== undefined && c !== undefined && !Number.isNaN(r) && !Number.isNaN(c) && (r !== row || c !== col)) {
            setActive({ row: r, col: c });
          }
        }}
      >
        <caption>{caption}</caption>
        <thead>
          <tr aria-rowindex={1}>
            {columns.map((column, c) => {
              const sorting = column.sortBy !== undefined && column.sortBy === sortColumn;
              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={sorting ? sort.direction : undefined}
                  className={column.numeric ? "numeric" : undefined}
                  tabIndex={column.sortBy ? undefined : tab(0, c)}
                  data-cell={column.sortBy ? undefined : `0:${c}`}
                >
                  {column.sortBy ? (
                    <button
                      type="button"
                      className="matrix-grid__sort"
                      tabIndex={tab(0, c)}
                      data-cell={`0:${c}`}
                      onClick={() => onSortBy(column)}
                    >
                      {column.header}
                      {sorting && <SortMark direction={sort.direction} />}
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {shown.rows.map((item, i) => {
            const r = i + 1;
            return (
              <tr
                key={item.id}
                aria-rowindex={shown.first + i + 1}
                aria-selected={isSelected(item)}
              >
                {columns.map((column, c) => {
                  if (column.action) {
                    const action = column.action;
                    return (
                      <td key={column.key}>
                        <button
                          type="button"
                          className="btn btn--quiet matrix-grid__action"
                          tabIndex={tab(r, c)}
                          data-cell={`${r}:${c}`}
                          aria-label={action.name(item)}
                          onClick={() => action.run(item)}
                        >
                          {action.text}
                        </button>
                      </td>
                    );
                  }
                  const Cell = column.rowHeader ? "th" : "td";
                  return (
                    <Cell
                      key={column.key}
                      scope={column.rowHeader ? "row" : undefined}
                      className={column.numeric ? "numeric" : undefined}
                      tabIndex={tab(r, c)}
                      data-cell={`${r}:${c}`}
                      onClick={(e) => onSelect(item, e.ctrlKey || e.metaKey)}
                    >
                      {column.render?.(item)}
                    </Cell>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      {shown.pages > 1 && (
        <div className="matrix-view__pager">
          <button
            type="button"
            className="btn"
            aria-label={`Previous page of ${noun}`}
            disabled={shown.page === 0}
            onClick={() => setPage(shown.page - 1)}
          >
            Previous
          </button>
          <span>
            Page {COUNT.format(shown.page + 1)} of {COUNT.format(shown.pages)}
          </span>
          <button
            type="button"
            className="btn"
            aria-label={`Next page of ${noun}`}
            disabled={shown.page === shown.pages - 1}
            onClick={() => setPage(shown.page + 1)}
          >
            Next
          </button>
        </div>
      )}
    </>
  );
}

function Provenance({ state }: { state: EntityRow["provenance"] }) {
  return <>{provenanceText(state)}</>;
}

function Marking({ marking }: { marking: string | null }) {
  return marking ? <span className="value marking-badge">{marking}</span> : null;
}

function Dimmed() {
  return <span className="matrix-grid__tag">Dimmed by filter</span>;
}

export function MatrixView({
  graph,
  store,
  edgeTypes,
  visualFor,
  dimmedNodeIds = NONE,
  dimmedEdgeIds = NONE,
  selectedNodeIds,
  selectedEdgeId,
  onSelectNodes,
  onSelectLink,
  onExpand,
  onShowOnGraph,
  strength,
}: MatrixViewProps) {
  // Every change to what the working set holds moves `seq` (`workingset/store.ts` is the only
  // place the graph's membership changes), so the rows are read again from the graph then.
  const seq = useStore(store, (s) => s.seq);
  const entities = useMemo(
    () => entityRows(graph, dimmedNodeIds),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graph, seq, dimmedNodeIds],
  );
  // ADR-139: each link's strength and its ends' rarity, worked out in the store as the reader each
  // time the view's links change; until then (or if refused) the columns say so.
  const [linkValues, setLinkValues] = useState<LinkValues>({});
  const [valuesProblem, setValuesProblem] = useState<string | null>(null);
  useEffect(() => {
    if (!strength) return;
    let cancelled = false;
    const pairs = new Map<string, [string, string]>();
    const byPair = new Map<string, string[]>();
    graph.forEachEdge((id, _attrs, source, target) => {
      const [a, b] = source < target ? [source, target] : [target, source];
      const key = `${a}\u0000${b}`;
      pairs.set(key, [a, b]);
      byPair.set(key, [...(byPair.get(key) ?? []), id]);
    });
    const { apiBaseUrl, bearerToken, investigationId } = strength;
    void Promise.all([
      fetchConnectionStrengths(apiBaseUrl, bearerToken, investigationId),
      fetchRarity(apiBaseUrl, bearerToken, investigationId, "dataset", [...pairs.values()]),
    ])
      .then(([found, rarity]) => {
        if (cancelled) return;
        const strengthById: Record<string, number> = {};
        for (const link of found.links) strengthById[link.edge_id] = link.strength;
        const rarityById: Record<string, number> = {};
        for (const pair of rarity.pairs) {
          if (pair.score === null || pair.score === undefined) continue;
          const [a, b] = pair.a < pair.b ? [pair.a, pair.b] : [pair.b, pair.a];
          for (const id of byPair.get(`${a}\u0000${b}`) ?? []) rarityById[id] = pair.score;
        }
        setLinkValues({ strength: strengthById, rarity: rarityById });
        setValuesProblem(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setValuesProblem(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, seq, strength?.investigationId]);
  const links = useMemo(
    () => linkRows(graph, edgeTypes, dimmedEdgeIds, linkValues),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graph, seq, edgeTypes, dimmedEdgeIds, linkValues],
  );
  const selected = useMemo(() => new Set(selectedNodeIds), [selectedNodeIds]);
  // The page to open on is read once, when the view opens: a later selection made here is on the
  // page already.
  const [openOn] = useState<string | null>(() => selectedNodeIds.find((id) => graph.hasNode(id)) ?? null);
  const [openOnLink] = useState<string | null>(() => selectedEdgeId);
  const keysId = "matrix-view-keys";

  // A selection that names nodes no longer held is reported back without them, as the canvas does.
  useEffect(() => {
    const present = selectedNodeIds.filter((id) => graph.hasNode(id));
    if (present.length !== selectedNodeIds.length) onSelectNodes(present);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seq]);

  const entityColumns: Column<EntityRow>[] = [
    {
      key: "name",
      header: "Name",
      sortBy: "name",
      rowHeader: true,
      render: (row) => (
        <>
          <span className="value">{row.name}</span>
          {row.dimmed && <Dimmed />}
        </>
      ),
    },
    { key: "type", header: "Type", sortBy: "type", render: (row) => <TypeChip type={row.type} visual={visualFor?.(row.type)} /> },
    { key: "marking", header: "Marking", sortBy: "marking", render: (row) => <Marking marking={row.marking} /> },
    { key: "provenance", header: "Provenance", sortBy: "provenance", render: (row) => <Provenance state={row.provenance} /> },
    { key: "links", header: "Links in view", sortBy: "links", numeric: true, render: (row) => COUNT.format(row.links) },
    {
      key: "expand",
      header: "Expand",
      action: { text: "Expand", name: (row) => `Expand ${row.name}`, run: (row) => onExpand(row.id) },
    },
    {
      key: "show",
      header: "On the graph",
      action: { text: "Show", name: (row) => `Show ${row.name} on the graph`, run: (row) => onShowOnGraph(row.id) },
    },
  ];

  const linkColumns: Column<LinkRow>[] = [
    {
      key: "type",
      header: "Link",
      sortBy: "type",
      rowHeader: true,
      render: (row) => (
        <>
          {row.type}
          {row.dimmed && <Dimmed />}
        </>
      ),
    },
    { key: "from", header: "From", sortBy: "from", render: (row) => <span className="value">{row.from}</span> },
    { key: "to", header: "To", sortBy: "to", render: (row) => <span className="value">{row.to}</span> },
    { key: "marking", header: "Marking", sortBy: "marking", render: (row) => <Marking marking={row.marking} /> },
    { key: "provenance", header: "Provenance", sortBy: "provenance", render: (row) => <Provenance state={row.provenance} /> },
    ...(strength
      ? ([
          {
            key: "strength",
            header: "Strength",
            sortBy: "strength",
            numeric: true,
            render: (row) => (row.strength === null ? "Not worked out" : STRENGTH.format(row.strength)),
          },
          {
            key: "rarity",
            header: "Rarity",
            sortBy: "rarity",
            numeric: true,
            render: (row) => (row.rarity === null ? "None" : STRENGTH.format(row.rarity)),
          },
        ] satisfies Column<LinkRow>[])
      : []),
  ];

  if (entities.length === 0) {
    return (
      <section className="matrix-view" aria-labelledby="matrix-view-heading">
        <h2 id="matrix-view-heading" className="matrix-view__heading">
          Matrix
        </h2>
        <p className="matrix-view__intro">
          Nothing is in this view yet. Search above, or open the Graph to start from what this case holds.
        </p>
      </section>
    );
  }

  return (
    <section className="matrix-view" aria-labelledby="matrix-view-heading">
      <h2 id="matrix-view-heading" className="matrix-view__heading">
        Matrix
      </h2>
      <p id={keysId} className="matrix-view__intro">
        What the graph holds, as tables. Arrow keys move between cells. Enter selects a row; Space adds it
        to the selection or takes it out.
      </p>
      <h3 className="matrix-view__subheading">Entities</h3>
      <Grid<EntityRow>
        noun="entities"
        rows={entities}
        columns={entityColumns}
        defaultSort="name"
        multiselectable
        isSelected={(row) => selected.has(row.id)}
        onSelect={(row, toggle) => {
          if (!toggle) {
            onSelectNodes([row.id]);
            return;
          }
          onSelectNodes(
            selected.has(row.id)
              ? selectedNodeIds.filter((id) => id !== row.id)
              : [...selectedNodeIds, row.id],
          );
        }}
        openOn={openOn}
        describedBy={keysId}
      />
      {links.length > 0 && (
        <>
          <h3 className="matrix-view__subheading">Links</h3>
          {strength && (
            <p className="matrix-view__intro">
              {valuesProblem ??
                "Strength is each link's stored strength with the influencers in the legend; rarity is how rare what its two ends share is, per dataset, over what you may see."}
            </p>
          )}
          <Grid<LinkRow>
            noun="links"
            rows={links}
            columns={linkColumns}
            defaultSort="from"
            multiselectable={false}
            isSelected={(row) => row.id === selectedEdgeId}
            onSelect={(row) => onSelectLink(row.id)}
            openOn={openOnLink}
            describedBy={keysId}
          />
        </>
      )}
    </section>
  );
}
