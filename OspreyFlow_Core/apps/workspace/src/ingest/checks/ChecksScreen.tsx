// The Ingest Studio's "Checks on load" step (`06_DECISIONS.md` ADR-133 decision 6, stage (d);
// `spec/09_INGEST_STUDIO.md` §5a): which of the case's and the deployment's load-time rules apply
// to this pipeline, and what a hit does here — loads with its alert, or holds the rows for a
// reviewer (before commit only). Engineers attach rules; they never write one here: the rules are
// written by analysts in the Monitoring place. A whole-deployment rule applies to every pipeline.
// Until someone chooses, every case rule judges this pipeline's loads.
import { useEffect, useState } from "react";

import type { LoadCheck, LoadChecksView } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Select } from "../../design/primitives/Select";
import { fetchChecks, saveChecks } from "../api";
import { RightButton } from "../studio/rightsGate";

export interface ChecksScreenProps {
  apiBaseUrl: string;
  investigationId: string;
  bearerToken: string;
  recipeId: string;
  /** Absent when the screen is hosted in the pipeline's drawer (ADR-108 Amendment 6.1: nothing replaces the canvas, so there is nothing to go back to). */
  onBack?: () => void;
}

type OnHit = "alert" | "hold";

const RUNS_WORDS: Record<string, string> = {
  pre_commit: "before each load commits",
  post_commit: "after each load commits",
};

/** The choice as the screen holds it: each attachable rule, attached or not, and what a hit does. */
export function initialChoice(view: LoadChecksView): Record<string, { on: boolean; onHit: OnHit }> {
  const chosen = new Map((view.checks ?? []).map((c) => [c.rule_id, c.on_hit ?? "alert"]));
  return Object.fromEntries(
    (view.available ?? []).map((rule) => [
      rule.rule_id,
      {
        // Before anyone chooses, every case rule applies: the screen starts from what is in force.
        on: rule.always_applies || (view.chosen ? chosen.has(rule.rule_id) : true),
        onHit: (chosen.get(rule.rule_id) ?? rule.authors_on_hit ?? "alert") as OnHit,
      },
    ]),
  );
}

/** What is sent: the attached rules and what a hit does; a whole-deployment rule is sent only when
 * a hit is chosen to hold here (it applies to every pipeline whatever is sent). */
export function checksToSend(view: LoadChecksView, choice: Record<string, { on: boolean; onHit: OnHit }>): LoadCheck[] {
  return (view.available ?? [])
    .filter((rule) => choice[rule.rule_id]?.on)
    .filter((rule) => !rule.always_applies || choice[rule.rule_id]?.onHit === "hold")
    .map((rule) => ({ rule_id: rule.rule_id, on_hit: rule.can_hold ? (choice[rule.rule_id]?.onHit ?? "alert") : "alert" }));
}

export function ChecksScreen({ apiBaseUrl, investigationId, bearerToken, recipeId, onBack }: ChecksScreenProps) {
  const [view, setView] = useState<LoadChecksView | null>(null);
  const [choice, setChoice] = useState<Record<string, { on: boolean; onHit: OnHit }>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchChecks(apiBaseUrl, bearerToken, investigationId, recipeId)
      .then((found) => {
        if (cancelled) return;
        setView(found);
        setChoice(initialChoice(found));
      })
      .catch((e: Error) => !cancelled && setProblem(e.message));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, recipeId]);

  function save() {
    if (!view) return;
    setBusy(true);
    setProblem(null);
    saveChecks(apiBaseUrl, bearerToken, investigationId, recipeId, checksToSend(view, choice))
      .then((saved) => {
        setView(saved);
        setChoice(initialChoice(saved));
        setSaid(`Saved: ${(saved.checks ?? []).length} rule(s) attached to this pipeline. Run Test to see the alerts its sample would raise.`);
      })
      .catch((e: Error) => setProblem(e.message))
      .finally(() => setBusy(false));
  }

  const rules = view?.available ?? [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-16)", padding: "var(--sp-16)", height: "100%", overflow: "auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
        {onBack && <Button onClick={onBack}>← Back to the pipeline</Button>}
        <h1 style={{ fontSize: "1.1em", margin: 0 }}>Load rules</h1>
      </div>
      <p className="label" style={{ margin: 0, maxWidth: 720 }}>
        Choose which rules judge this pipeline&apos;s loads and what a hit does here. Rules are written by
        analysts in Monitoring; here you attach them. A rule for the whole deployment applies to every
        pipeline.
        {view && !view.chosen ? " Nothing has been chosen yet, so every rule of the case judges these loads." : ""}
      </p>
      {problem && (
        <p role="alert" style={{ color: "var(--error)", margin: 0 }}>
          {problem}
        </p>
      )}
      {said && (
        <p role="status" className="label" style={{ margin: 0 }}>
          {said}
        </p>
      )}
      {view && rules.length === 0 && <p className="label">No rule of this case or the deployment judges loads yet.</p>}
      {rules.length > 0 && (
        <table className="table" aria-label="Rules this pipeline may be checked by">
          <thead>
            <tr>
              <th>Apply</th>
              <th>Rule</th>
              <th>Runs</th>
              <th>A hit here</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => {
              const state = choice[rule.rule_id] ?? { on: false, onHit: "alert" as OnHit };
              return (
                <tr key={rule.rule_id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Apply ${rule.name}`}
                      checked={state.on}
                      disabled={rule.always_applies}
                      onChange={(e) => setChoice({ ...choice, [rule.rule_id]: { ...state, on: e.target.checked } })}
                    />
                  </td>
                  <td>
                    <span className="value">{rule.name}</span>
                    <br />
                    <span className="label">
                      {rule.scope === "deployment" ? "Whole deployment · applies to every pipeline" : "This case"}
                      {` · ${rule.severity} severity`}
                      {rule.status === "pending" ? " · waiting for a second person's approval: it does not run yet" : ""}
                    </span>
                    <br />
                    <span className="label">{rule.words}</span>
                  </td>
                  <td className="label">{RUNS_WORDS[rule.trigger] ?? rule.trigger}</td>
                  <td>
                    {rule.can_hold ? (
                      <Select
                        aria-label={`A hit of ${rule.name}`}
                        value={state.onHit}
                        disabled={!state.on || (rule.always_applies && rule.authors_on_hit === "hold")}
                        onChange={(e) => setChoice({ ...choice, [rule.rule_id]: { ...state, onHit: e.target.value as OnHit } })}
                      >
                        <option value="alert">loads with an alert</option>
                        <option value="hold">holds the rows for review</option>
                      </Select>
                    ) : (
                      <span className="label">loads with an alert (it runs after commit)</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <div>
        <RightButton right="edit_pipelines" variant="primary" disabled={busy || !view} onClick={save}>
          Save the load rules
        </RightButton>
      </div>
    </div>
  );
}
