// Find connections (ADR-116): how two people, or any two nodes, are connected, by degrees.
//
// From and To are each found by search over the case's datasets or taken from the node selected on
// the canvas, so neither need be drawn. The panel first asks for the fewest degrees that connect them
// and lists the routes there; each Show routes at N degrees widens by one, to ADR-033's ceiling of
// eight, and each degree keeps its own group so a longer route never hides a shorter one. A degree
// with more routes than are shown says so (rule 2). A route can be put on the canvas, its nodes then
// marked with their degree from From.
import { useState } from "react";

import type { Node, Path } from "../../../../packages/schemas/generated";
import type { WorkingSetDelta } from "../workingset/models";
import { Button } from "../design/primitives/Button";
import { Panel } from "../design/primitives/Panel";
import { GlobalSearch } from "../search/GlobalSearch";
import { displayValue } from "../search/searchOptions";
import {
  degreeMarks,
  degreesApart,
  findConnections,
  routeCountWords,
  routeOnCanvas,
  seedRoute,
  type CanvasContents,
} from "./connectionsApi";

/** ADR-116 decision 2 and ADR-033: the furthest a search may be widened. */
export const CONNECTIONS_CEILING = 8;

export interface FindConnectionsPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The node selected on the canvas now, for Use the selected node. */
  selected: Node | null;
  /** What is on the canvas, to say which routes are already there. */
  canvas: CanvasContents;
  /** Draws what a route added to the working set. */
  onDelta: (delta: WorkingSetDelta) => void;
  /** Marks each node of an added route with its degree from From. */
  onMark: (marks: Map<string, number>) => void;
  onClearMarks: () => void;
}

interface DegreeGroup {
  degree: number;
  paths: Path[];
  more: boolean;
}

interface Search {
  from: Node;
  to: Node;
  /** The fewest degrees connecting them, or null when none was found up to `searchedTo`. */
  fewest: number | null;
  searchedTo: number;
  groups: DegreeGroup[];
}

const routeKey = (degree: number, index: number) => `${degree}:${index}`;

function EndChooser({
  end,
  chosen,
  selected,
  onChoose,
  search,
}: {
  end: "From" | "To";
  chosen: Node | null;
  selected: Node | null;
  onChoose: (node: Node) => void;
  search: { apiBaseUrl: string; bearerToken: string; investigationId: string };
}) {
  return (
    <div role="group" aria-label={end} style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
      <GlobalSearch {...search} label={`Search for ${end}`} slashFocuses={false} onSelect={onChoose} />
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)", flexWrap: "wrap" }}>
        <Button
          type="button"
          aria-disabled={selected === null}
          title={selected === null ? "Select a node on the canvas first" : undefined}
          onClick={() => {
            if (selected) onChoose(selected);
          }}
        >
          {`Use the selected node as ${end}`}
        </Button>
        {chosen && <span className="value">{`${end}: ${displayValue(chosen)}`}</span>}
      </div>
    </div>
  );
}

export function FindConnectionsPanel({
  apiBaseUrl,
  bearerToken,
  investigationId,
  selected,
  canvas,
  onDelta,
  onMark,
  onClearMarks,
}: FindConnectionsPanelProps) {
  const context = { apiBaseUrl, bearerToken, investigationId };
  const [from, setFrom] = useState<Node | null>(null);
  const [to, setTo] = useState<Node | null>(null);
  const [found, setFound] = useState<Search | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<ReadonlySet<string>>(new Set());
  const [marked, setMarked] = useState(false);

  const same = from !== null && to !== null && from.id === to.id;
  const ready = from !== null && to !== null && !same && !busy;

  const choose = (set: (node: Node) => void) => (node: Node) => {
    set(node);
    setFound(null);
    setError(null);
    setAdded(new Set());
  };

  async function search(): Promise<void> {
    if (!ready || !from || !to) return;
    setBusy(true);
    setError(null);
    try {
      const answer = await findConnections(context, from.id, to.id);
      setAdded(new Set());
      setFound({
        from,
        to,
        fewest: answer.degree,
        searchedTo: answer.searched_to,
        groups: answer.degree === null ? [] : [{ degree: answer.degree, paths: answer.paths, more: answer.more }],
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function widen(current: Search, degree: number): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const answer = await findConnections(context, current.from.id, current.to.id, degree);
      setFound({
        ...current,
        searchedTo: degree,
        groups: [...current.groups, { degree, paths: answer.paths, more: answer.more }],
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function add(route: Path, key: string): Promise<void> {
    setError(null);
    try {
      const delta = await seedRoute(context, route, canvas);
      if (delta) onDelta(delta);
      onMark(degreeMarks(route));
      setMarked(true);
      setAdded((prev) => new Set(prev).add(key));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const next = found ? found.searchedTo + 1 : null;

  return (
    <Panel className="find-connections-panel">
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
        <EndChooser end="From" chosen={from} selected={selected} onChoose={choose(setFrom)} search={context} />
        <EndChooser end="To" chosen={to} selected={selected} onChoose={choose(setTo)} search={context} />
        {same && <p style={{ margin: 0, color: "var(--text-secondary)" }}>From and To are the same node.</p>}
        <div style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
          <Button type="button" variant="primary" aria-disabled={!ready} onClick={() => void search()}>
            Find connections
          </Button>
          {marked && (
            <Button
              type="button"
              onClick={() => {
                onClearMarks();
                setMarked(false);
              }}
            >
              Clear the degree marks
            </Button>
          )}
        </div>
        {error && (
          <p role="alert" style={{ margin: 0, color: "var(--error)" }}>
            {error}
          </p>
        )}
        {found && (
          <p role="status" style={{ margin: 0 }}>
            {found.fewest === null
              ? `${displayValue(found.from)} and ${displayValue(found.to)} are not connected within ${found.searchedTo} degrees.`
              : `${displayValue(found.from)} and ${displayValue(found.to)} are ${degreesApart(found.fewest)}.`}
          </p>
        )}
        {found?.groups.map((group) => {
          const heading = routeCountWords({ degree: group.degree, count: group.paths.length, more: group.more });
          return (
            <section key={group.degree} aria-label={heading} style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
              <h3 style={{ margin: 0, fontSize: "var(--fs-12)", fontWeight: 600 }}>{heading}</h3>
              <ol style={{ margin: 0, paddingLeft: "var(--sp-16)", display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
                {group.paths.map((route, index) => {
                  const key = routeKey(group.degree, index);
                  const there = added.has(key) || routeOnCanvas(route, canvas);
                  return (
                    <li key={key}>
                      <span>{route.nodes.map((n) => displayValue(n)).join(" → ")}</span>{" "}
                      {there ? (
                        <span style={{ color: "var(--text-tertiary)" }}>On the canvas</span>
                      ) : (
                        <Button
                          type="button"
                          className="btn--quiet"
                          aria-label={`Add route ${index + 1} at ${group.degree} ${group.degree === 1 ? "degree" : "degrees"} to the canvas`}
                          onClick={() => void add(route, key)}
                        >
                          Add to canvas
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ol>
            </section>
          );
        })}
        {found && next !== null && next <= CONNECTIONS_CEILING && (
          <div>
            <Button type="button" aria-disabled={busy} onClick={() => void (busy ? undefined : widen(found, next))}>
              {`Show routes at ${next} degrees`}
            </Button>
          </div>
        )}
      </div>
    </Panel>
  );
}
