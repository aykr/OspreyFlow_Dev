// The visual query builder's own panel — Phase 7 Stage 4, `02_GLASS_FRONTEND.md` §3.3, B19
// (`08_ACCEPTANCE_SCENARIOS.md`). Pairs with `store.ts` (pure pattern state/validation) the same
// way `MetricsPanel.tsx` pairs with `metrics/hulls.ts`.
//
// **Pinning is how a node is placed, not a checkbox after the fact** — `06_DECISIONS.md` ADR-030's
// own "explained at the point of drawing" standard. There are exactly two ways to add a pattern
// node: "Add variable" (an ordinary, unpinned entity-type placeholder) and searching for a known
// node via `GlobalSearch` (which always pins — there is no "search, then leave it unpinned"
// path). `unpinnedSecondaryRoots` re-derives, on every render, whether the pattern as drawn right
// now needs a pin it doesn't have — the same derivation `MatchBuilder._render_matched` uses
// server-side — so the "needs pinning" cue appears and clears live as edges are drawn or removed,
// not only when Preview/Run is pressed.
//
// **Delete/Backspace on a focused pattern node** removes it (and every edge touching it) — real
// state-mutating logic, not a native control, so it gets its own `keyboard/query-builder.spec.ts`
// case (`delete-focused-pattern-element`) the same way `MetricsPanel`'s row activation does.
//
// **Save/load — Phase 7 Stage 4's own "saveable ... and versioned" promise, closed here
// (`06_DECISIONS.md` ADR-032/036/040).** Save always writes the *next version* of whatever pattern
// is currently loaded (`currentPatternId`), or starts a brand-new one if nothing is loaded yet —
// there is no separate "save as new" control, matching the store's own `pattern_id=None` shape.
// No share control exists: ADR-040 (pattern sharing) is Proposed, not accepted, so a saved pattern
// is loadable only by the analyst who saved it.
import { useEffect, useMemo, useState } from "react";
import type { KeyboardEvent } from "react";

import type { Node, OntologySchema, SavedPattern } from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives/Button";
import { Input } from "../design/primitives/Input";
import { AccordionSection } from "../design/primitives/AccordionSection";
import { Panel } from "../design/primitives/Panel";
import { Select } from "../design/primitives/Select";
import { GlobalSearch } from "../search/GlobalSearch";
import {
  fetchPatternPreview,
  listPatterns,
  loadPattern,
  runPattern,
  savePattern,
  type PatternPreview,
  type PatternRunAccepted,
} from "./api";
import {
  addEdge,
  addVariableNode,
  createEmptyPattern,
  fromPatternQuery,
  isPatternRunnable,
  pinNode,
  removeElement,
  toPatternQuery,
  unpinnedSecondaryRoots,
  type PatternBuilderState,
} from "./store";

export interface QueryBuilderPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** ADR-099: the case the pattern is matched in. */
  investigationId: string;
  schema: OntologySchema;
}

/** The parts the Query builder folds into (ADR-096). */
type QueryBuilderPart = "pattern" | "add" | "connect" | "save";

export function QueryBuilderPanel({ apiBaseUrl, bearerToken, investigationId, schema }: QueryBuilderPanelProps) {
  const [pattern, setPattern] = useState<PatternBuilderState>(createEmptyPattern());
  const [paletteType, setPaletteType] = useState(schema.entity_types[0]?.name ?? "");
  const [connectFrom, setConnectFrom] = useState("");
  const [connectTo, setConnectTo] = useState("");
  const [connectEdgeType, setConnectEdgeType] = useState(schema.edge_types[0]?.name ?? "");
  const [preview, setPreview] = useState<PatternPreview | null>(null);
  const [runResult, setRunResult] = useState<PatternRunAccepted | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [patternName, setPatternName] = useState("");
  const [currentPatternId, setCurrentPatternId] = useState<string | null>(null);
  const [savedPatterns, setSavedPatterns] = useState<SavedPattern[]>([]);
  const [selectedPatternId, setSelectedPatternId] = useState("");
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  useEffect(() => {
    // Silently leaves the list empty on failure — an analyst who has never saved anything, or
    // whose session can't reach `/v1/patterns` yet, sees an empty "Load" select rather than an
    // error banner before they have done anything. `handleSave`/`handleLoad` surface a real
    // `error` state for a failure the analyst actually triggered.
    listPatterns(apiBaseUrl, bearerToken)
      .then(setSavedPatterns)
      .catch(() => undefined);
    // Only ever needs to run once, on mount — `handleSave` and `handleLoad` each refresh the list
    // themselves after their own network call completes, rather than this effect re-running.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const flaggedVars = useMemo(
    () => new Set(unpinnedSecondaryRoots(pattern).map((n) => n.var)),
    [pattern],
  );
  const runnable = isPatternRunnable(pattern);

  function resetResults(): void {
    setPreview(null);
    setRunResult(null);
    setError(null);
  }

  function handleAddVariable(): void {
    if (!paletteType) return;
    setPattern((p) => addVariableNode(p, paletteType));
    resetResults();
  }

  function handlePinFromSearch(node: Node): void {
    setPattern((p) => pinNode(p, node.type, node.id, `${node.type} · ${node.id}`));
    resetResults();
  }

  function handleConnect(): void {
    if (!connectFrom || !connectTo || !connectEdgeType) return;
    setPattern((p) => addEdge(p, connectEdgeType, connectFrom, connectTo));
    resetResults();
  }

  function handleNodeKeyDown(nodeVar: string, event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      setPattern((p) => removeElement(p, nodeVar));
      resetResults();
    }
  }

  async function handlePreview(): Promise<void> {
    setError(null);
    try {
      setPreview(await fetchPatternPreview(apiBaseUrl, bearerToken, investigationId, toPatternQuery(pattern)));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleRun(): Promise<void> {
    setError(null);
    try {
      setRunResult(await runPattern(apiBaseUrl, bearerToken, investigationId, toPatternQuery(pattern)));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleSave(): Promise<void> {
    setError(null);
    setSaveStatus(null);
    try {
      const saved = await savePattern(apiBaseUrl, bearerToken, {
        pattern_id: currentPatternId,
        name: patternName || "Untitled pattern",
        definition: toPatternQuery(pattern),
      });
      setCurrentPatternId(saved.pattern_id);
      setSaveStatus(`Saved as version ${saved.version}.`);
      setSavedPatterns(await listPatterns(apiBaseUrl, bearerToken));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleLoad(): Promise<void> {
    if (!selectedPatternId) return;
    setError(null);
    setSaveStatus(null);
    try {
      const saved = await loadPattern(apiBaseUrl, bearerToken, selectedPatternId);
      setPattern(fromPatternQuery(saved.definition));
      setCurrentPatternId(saved.pattern_id);
      setPatternName(saved.name);
      resetResults();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const [parts, setParts] = useState<ReadonlySet<QueryBuilderPart>>(() => new Set(["pattern"]));
  const togglePart = (part: QueryBuilderPart) =>
    setParts((current) => {
      const next = new Set(current);
      if (next.has(part)) next.delete(part);
      else next.add(part);
      return next;
    });

  return (
    <Panel title="Query builder" className="query-builder-panel">
      {/* ADR-096: the panel opens on its preview, the pattern with Preview and Run and what they
          answer; adding, connecting, saving and loading fold away under their own headers. */}
      <div style={{ display: "flex", flexDirection: "column" }}>
        <AccordionSection title="Pattern" open={parts.has("pattern")} onToggle={() => togglePart("pattern")}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)" }}>
        {pattern.nodes.length === 0 && (
          <p style={{ margin: 0, color: "var(--text-tertiary)" }}>
            No pattern yet: open Add to the pattern to start one.
          </p>
        )}
        <ul
          role="list"
          aria-label="Pattern nodes"
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-4)",
          }}
        >
          {pattern.nodes.map((n) => {
            const needsPinning = flaggedVars.has(n.var);
            return (
              <li key={n.var}>
                <div
                  tabIndex={0}
                  role="group"
                  aria-label={`Pattern node ${n.var}: ${n.pinnedLabel ?? n.entityType}`}
                  className="query-builder-panel__node"
                  data-needs-pinning={needsPinning ? "true" : undefined}
                  onKeyDown={(e) => handleNodeKeyDown(n.var, e)}
                  style={{
                    border: needsPinning ? "2px dashed var(--warning)" : "1px solid var(--border)",
                    borderRadius: "var(--radius-panel, 4px)",
                    padding: "var(--sp-4)",
                  }}
                >
                  <strong>{n.var}</strong>: {n.pinnedLabel ?? n.entityType}
                  {needsPinning && (
                    <span role="status" aria-live="polite" style={{ display: "block" }}>
                      Second root — pin to a known node or connect it to the pattern
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>

        {error && <p style={{ color: "var(--error)" }}>{error}</p>}

        <div style={{ display: "flex", gap: "var(--sp-8)" }}>
          <Button type="button" onClick={() => void handlePreview()} disabled={!runnable}>
            Preview
          </Button>
          <Button
            type="button"
            variant="primary"
            onClick={() => void handleRun()}
            disabled={!runnable}
          >
            Run
          </Button>
        </div>

        {preview && (
          <p aria-live="polite">
            {preview.is_floor ? `${preview.estimated_count}+ matches` : `~${preview.estimated_count} matches`}
          </p>
        )}
        {runResult?.mode === "sync" && <p aria-live="polite">{runResult.matched_count} node(s) matched.</p>}
        {runResult?.mode === "job" && (
          <p aria-live="polite">Large result — running as job {runResult.job_id}.</p>
        )}
        </div>
        </AccordionSection>
        <AccordionSection title="Add to the pattern" open={parts.has("add")} onToggle={() => togglePart("add")}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)" }}>
        <div
          role="group"
          aria-label="Add a pattern variable"
          style={{ display: "flex", gap: "var(--sp-4)" }}
        >
          <Select
            aria-label="Entity type"
            value={paletteType}
            onChange={(e) => setPaletteType(e.target.value)}
          >
            {schema.entity_types.map((t) => (
              <option key={t.name} value={t.name}>
                {t.name}
              </option>
            ))}
          </Select>
          <Button type="button" onClick={handleAddVariable}>
            Add variable
          </Button>
        </div>

        <GlobalSearch
          apiBaseUrl={apiBaseUrl}
          bearerToken={bearerToken}
          investigationId={investigationId}
          onSelect={handlePinFromSearch}
        />

        </div>
        </AccordionSection>
        {pattern.nodes.length >= 2 && (
        <AccordionSection title="Connect" open={parts.has("connect")} onToggle={() => togglePart("connect")}>

          <div
            role="group"
            aria-label="Connect two pattern nodes"
            style={{ display: "flex", gap: "var(--sp-4)" }}
          >
            <Select aria-label="From" value={connectFrom} onChange={(e) => setConnectFrom(e.target.value)}>
              <option value="">From…</option>
              {pattern.nodes.map((n) => (
                <option key={n.var} value={n.var}>
                  {n.var}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Edge type"
              value={connectEdgeType}
              onChange={(e) => setConnectEdgeType(e.target.value)}
            >
              {schema.edge_types.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </Select>
            <Select aria-label="To" value={connectTo} onChange={(e) => setConnectTo(e.target.value)}>
              <option value="">To…</option>
              {pattern.nodes.map((n) => (
                <option key={n.var} value={n.var}>
                  {n.var}
                </option>
              ))}
            </Select>
            <Button type="button" onClick={handleConnect}>
              Connect
            </Button>
          </div>
        
        </AccordionSection>
        )}
        <AccordionSection title="Save and load" open={parts.has("save")} onToggle={() => togglePart("save")}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)" }}>
        <div
          role="group"
          aria-label="Save this pattern"
          style={{ display: "flex", gap: "var(--sp-4)" }}
        >
          <Input
            aria-label="Pattern name"
            value={patternName}
            onChange={(e) => setPatternName(e.target.value)}
            placeholder="Untitled pattern"
          />
          <Button type="button" onClick={() => void handleSave()} disabled={pattern.nodes.length === 0}>
            {currentPatternId ? "Save new version" : "Save"}
          </Button>
        </div>
        {saveStatus && <p aria-live="polite">{saveStatus}</p>}

        <div
          role="group"
          aria-label="Load a saved pattern"
          style={{ display: "flex", gap: "var(--sp-4)" }}
        >
          <Select
            aria-label="Saved patterns"
            value={selectedPatternId}
            onChange={(e) => setSelectedPatternId(e.target.value)}
          >
            <option value="">Choose a saved pattern…</option>
            {savedPatterns.map((p) => (
              <option key={p.pattern_id} value={p.pattern_id}>
                {p.name} (v{p.version})
              </option>
            ))}
          </Select>
          <Button type="button" onClick={() => void handleLoad()} disabled={!selectedPatternId}>
            Load
          </Button>
        </div>

        </div>
        </AccordionSection>
      </div>
    </Panel>
  );
}
