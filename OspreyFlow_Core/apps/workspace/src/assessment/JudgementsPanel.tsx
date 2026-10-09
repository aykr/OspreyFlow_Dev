// The Judgements tab — `02_GLASS_FRONTEND.md` §9, Phase 8 Stage 4c. Judgement/gap/assumption
// authoring, bidirectional evidence highlighting, yardstick band display, the review-flag chip.
//
// **Errors surface as an inline banner, not `ActionErrorOverlay`** — the same reasoning
// `watches/AlertInbox.tsx`'s own header comment already gives: this panel has no cursor position
// or canvas selection for a failure to anchor to (`02_GLASS_FRONTEND.md` §4.1's own "panel inline
// banner — non-canvas surfaces" rule).
import type Graph from "graphology";
import { useEffect, useMemo, useState } from "react";

import { Button } from "../design/primitives/Button";
import { Combobox } from "../design/primitives/Combobox";
import { Drawer } from "../design/primitives/Drawer";
import { Input } from "../design/primitives/Input";
import { Select } from "../design/primitives/Select";
import { Table } from "../design/primitives/Table";
import { Tabs } from "../design/primitives/Tabs";
import {
  getYardstick,
  listAssumptions,
  listGaps,
  listJudgements,
  saveAssumption,
  saveGap,
  saveJudgement,
  UnverifiableCitationApiError,
  type Yardstick,
} from "./api";
import { ReviewFlagChip } from "./ReviewFlagChip";

import type { Assumption, IntelligenceGap, Judgement } from "../../../../packages/schemas/generated";

export interface JudgementsPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The working set's own graphology instance — the evidence picker's *only* source of
   * options. Citation-type restriction (Part 1 of this session): only ever offers node-shaped
   * evidence, since `graph.nodes()` structurally cannot contain an edge or a document — there is
   * no "attach a document"/"attach a relationship" option to build in the first place, because
   * neither is ever a candidate value here. */
  workingSetGraph: Graph;
  /** The currently node-selected-on-canvas id, or `null` — `02_GLASS_FRONTEND.md` §9.2: "selecting
   * a node lists the judgements that rest on it," filtered here rather than a second fetch. */
  selectedNodeId: string | null;
  /** `02_GLASS_FRONTEND.md` §9.2: "selecting a judgement highlights its own supporting/
   * contradicting items on the canvas" — `GlassCanvasHandle.highlightNodes`, threaded through by
   * the caller (`App.tsx`) rather than this panel owning a canvas ref of its own. */
  onHighlightNodes: (nodeIds: string[]) => void;
  /** Called with the whole list each time it has been fetched, so the canvas can show a count
   * beside each node with judgements (ADR-070). */
  onJudgementsChange?: (judgements: Judgement[]) => void;
}

type DrawerTab = "judgement" | "gap" | "assumption";

function nodeLabel(graph: Graph, nodeId: string): string {
  if (!graph.hasNode(nodeId)) return nodeId;
  const data = graph.getNodeAttribute(nodeId, "data") as
    | { type?: string; properties?: Record<string, unknown> }
    | undefined;
  const name =
    (data?.properties?.family_name as string | undefined) ??
    (data?.properties?.value_normalised as string | undefined);
  return name ? `${data?.type ?? "Node"}: ${name}` : nodeId;
}

/** A `Combobox` (add) plus a chip list (remove) — the shared shape both the judgement/gap
 * evidence picker and the assumption's linked-judgement picker need. Generic over the option
 * shape rather than duplicated per caller. */
function MultiPicker({
  options,
  selected,
  onChange,
  ariaLabel,
}: {
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (next: string[]) => void;
  ariaLabel: string;
}) {
  const available = options.filter((o) => !selected.includes(o.value));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
      <Combobox
        aria-label={ariaLabel}
        options={available}
        value=""
        onChange={(value) => onChange([...selected, value])}
        placeholder={ariaLabel}
      />
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexWrap: "wrap", gap: "var(--sp-4)" }}>
        {selected.map((value) => {
          const option = options.find((o) => o.value === value);
          return (
            <li
              key={value}
              className="value"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--sp-4)",
                padding: "2px var(--sp-8)",
                borderRadius: "999px",
                background: "var(--surface-raised)",
              }}
            >
              {option?.label ?? value}
              <button
                type="button"
                aria-label={`Remove ${option?.label ?? value}`}
                onClick={() => onChange(selected.filter((id) => id !== value))}
                style={{ background: "none", border: "none", cursor: "pointer", color: "inherit" }}
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function JudgementsPanel({
  apiBaseUrl,
  bearerToken,
  investigationId,
  workingSetGraph,
  selectedNodeId,
  onHighlightNodes,
  onJudgementsChange,
}: JudgementsPanelProps) {
  const [judgements, setJudgements] = useState<Judgement[]>([]);
  const [gaps, setGaps] = useState<IntelligenceGap[]>([]);
  const [assumptions, setAssumptions] = useState<Assumption[]>([]);
  const [yardstick, setYardstick] = useState<Yardstick | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("judgement");
  const [saving, setSaving] = useState(false);

  const [statement, setStatement] = useState("");
  const [band, setBand] = useState("");
  const [supporting, setSupporting] = useState<string[]>([]);
  const [contradicting, setContradicting] = useState<string[]>([]);

  const [question, setQuestion] = useState("");
  const [linkedEntities, setLinkedEntities] = useState<string[]>([]);

  const [assumptionStatement, setAssumptionStatement] = useState("");
  const [ifFalseImpact, setIfFalseImpact] = useState("");
  const [linkedJudgements, setLinkedJudgements] = useState<string[]>([]);

  function refresh(): void {
    listJudgements(apiBaseUrl, bearerToken, investigationId)
      .then((list) => {
        setJudgements(list);
        onJudgementsChange?.(list);
      })
      .catch(() => undefined);
    listGaps(apiBaseUrl, bearerToken, investigationId).then(setGaps).catch(() => undefined);
    listAssumptions(apiBaseUrl, bearerToken, investigationId).then(setAssumptions).catch(() => undefined);
  }

  useEffect(() => {
    refresh();
    getYardstick(apiBaseUrl, bearerToken).then((y) => {
      setYardstick(y);
      setBand((current) => current || y.bands[0]?.label || "");
    }).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigationId]);

  // Read from the working set on every render, not memoised on it: the canvas fills the same graph
  // in place, so a memo keyed on it was worked out once, at page load, empty (9 October 2026).
  const nodeOptions = workingSetGraph
    .nodes()
    .map((id) => ({ value: id, label: nodeLabel(workingSetGraph, id) }));

  const judgementOptions = useMemo(
    () => judgements.map((j) => ({ value: j.id, label: j.statement.slice(0, 60) })),
    [judgements],
  );

  // `02_GLASS_FRONTEND.md` §9.2: "selecting a node lists the judgements that rest on it" —
  // filtered here, not a second fetch, since the full list is already in hand.
  const visibleJudgements = selectedNodeId
    ? judgements.filter(
        (j) =>
          (j.supporting ?? []).includes(selectedNodeId) ||
          (j.contradicting ?? []).includes(selectedNodeId),
      )
    : judgements;

  function resetForms(): void {
    setStatement("");
    setSupporting([]);
    setContradicting([]);
    setQuestion("");
    setLinkedEntities([]);
    setAssumptionStatement("");
    setIfFalseImpact("");
    setLinkedJudgements([]);
  }

  async function handleSaveJudgement(): Promise<void> {
    setError(null);
    setSaving(true);
    try {
      await saveJudgement(apiBaseUrl, bearerToken, investigationId, {
        investigation_id: investigationId,
        statement,
        probability_band: band,
        supporting,
        contradicting,
      });
      resetForms();
      setDrawerOpen(false);
      refresh();
    } catch (err) {
      if (err instanceof UnverifiableCitationApiError) {
        setError(`${err.message} (${err.citationIds.join(", ")})`);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveGap(): Promise<void> {
    setError(null);
    setSaving(true);
    try {
      await saveGap(apiBaseUrl, bearerToken, investigationId, {
        investigation_id: investigationId,
        question,
        linked_entities: linkedEntities,
        status: "open",
      });
      resetForms();
      setDrawerOpen(false);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveAssumption(): Promise<void> {
    setError(null);
    setSaving(true);
    try {
      await saveAssumption(apiBaseUrl, bearerToken, investigationId, {
        investigation_id: investigationId,
        statement: assumptionStatement,
        if_false_impact: ifFalseImpact,
        linked_judgements: linkedJudgements,
      });
      resetForms();
      setDrawerOpen(false);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="judgements-panel" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
      {error && (
        <p role="alert" style={{ color: "var(--error)" }}>
          {error}
        </p>
      )}
      {selectedNodeId && (
        <p className="label">Showing judgements resting on the selected node.</p>
      )}
      <Table<Judgement>
        columns={[
          {
            key: "statement",
            header: "Statement",
            render: (j) => (
              <button
                type="button"
                className="value"
                style={{ background: "none", border: "none", cursor: "pointer", textAlign: "left", padding: 0 }}
                onClick={() => onHighlightNodes([...(j.supporting ?? []), ...(j.contradicting ?? [])])}
              >
                {j.statement.length > 60 ? `${j.statement.slice(0, 60)}…` : j.statement}
              </button>
            ),
          },
          { key: "band", header: "Band", render: (j) => j.probability_band },
          { key: "evidence", header: "Evidence", render: (j) => `${(j.supporting ?? []).length}` },
          {
            key: "flag",
            header: "",
            render: (j) => (j.flagged_for_review && j.flag_reason ? <ReviewFlagChip reason={j.flag_reason} /> : null),
          },
        ]}
        rows={visibleJudgements}
        getRowId={(j) => j.id}
      />

      {gaps.length > 0 && (
        <div>
          <h3 className="panel__title" style={{ fontSize: "var(--fs-13)" }}>
            Intelligence gaps
          </h3>
          <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
            {gaps.map((g) => (
              <li key={g.id} className="value">
                {g.question} <span className="label">({g.status})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {assumptions.length > 0 && (
        <div>
          <h3 className="panel__title" style={{ fontSize: "var(--fs-13)" }}>
            Assumptions
          </h3>
          <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
            {assumptions.map((a) => (
              <li key={a.id} className="value">
                {a.statement}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Button variant="primary" onClick={() => setDrawerOpen(true)}>
        Add judgement, gap or assumption
      </Button>

      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Record an assessment">
        <Tabs
          tabs={[
            { id: "judgement", label: "Judgement" },
            { id: "gap", label: "Gap" },
            { id: "assumption", label: "Assumption" },
          ]}
          activeId={drawerTab}
          onChange={(id) => setDrawerTab(id as DrawerTab)}
        />

        {drawerTab === "judgement" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)", marginTop: "var(--sp-8)" }}>
            <label>
              Statement
              <Input value={statement} onChange={(e) => setStatement(e.target.value)} />
            </label>
            <label>
              Probability band
              <Select value={band} onChange={(e) => setBand(e.target.value)}>
                {(yardstick?.bands ?? []).map((b) => (
                  <option key={b.label} value={b.label}>
                    {b.label} ({b.lower}–{b.upper})
                  </option>
                ))}
              </Select>
            </label>
            <label>
              Supporting evidence
              <MultiPicker
                options={nodeOptions}
                selected={supporting}
                onChange={setSupporting}
                ariaLabel="Add supporting evidence"
              />
            </label>
            <label>
              Contradicting evidence
              <MultiPicker
                options={nodeOptions}
                selected={contradicting}
                onChange={setContradicting}
                ariaLabel="Add contradicting evidence"
              />
            </label>
            {/* A13's own literal assertion, rendered as a disabled Save rather than a post-submit
             * error — `02_GLASS_FRONTEND.md` §9.1: "the Save Button is disabled... until at least
             * one evidence item is attached." */}
            <Button
              variant="primary"
              disabled={statement.trim().length === 0 || supporting.length === 0 || saving}
              onClick={() => void handleSaveJudgement()}
            >
              {saving ? "Saving…" : "Save judgement"}
            </Button>
          </div>
        )}

        {drawerTab === "gap" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)", marginTop: "var(--sp-8)" }}>
            <label>
              Question
              <Input value={question} onChange={(e) => setQuestion(e.target.value)} />
            </label>
            <label>
              Linked entities
              <MultiPicker
                options={nodeOptions}
                selected={linkedEntities}
                onChange={setLinkedEntities}
                ariaLabel="Add linked entity"
              />
            </label>
            <Button
              variant="primary"
              disabled={question.trim().length === 0 || saving}
              onClick={() => void handleSaveGap()}
            >
              {saving ? "Saving…" : "Save gap"}
            </Button>
          </div>
        )}

        {drawerTab === "assumption" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)", marginTop: "var(--sp-8)" }}>
            <label>
              Statement
              <Input value={assumptionStatement} onChange={(e) => setAssumptionStatement(e.target.value)} />
            </label>
            <label>
              If false, the impact is
              <Input value={ifFalseImpact} onChange={(e) => setIfFalseImpact(e.target.value)} />
            </label>
            <label>
              Linked judgements
              <MultiPicker
                options={judgementOptions}
                selected={linkedJudgements}
                onChange={setLinkedJudgements}
                ariaLabel="Add linked judgement"
              />
            </label>
            <Button
              variant="primary"
              disabled={
                assumptionStatement.trim().length === 0 || ifFalseImpact.trim().length === 0 || saving
              }
              onClick={() => void handleSaveAssumption()}
            >
              {saving ? "Saving…" : "Save assumption"}
            </Button>
          </div>
        )}
      </Drawer>
    </div>
  );
}
