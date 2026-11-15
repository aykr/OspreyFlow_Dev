// What an Ask & Chat answer's items can be put to (v0.6.0 #5): *Show all on graph* puts every item the answer's markers
// stand for on the canvas and selects them; *Save as a view* saves that set as a saved view of the case (ADR-145
// Amendment 17: a saved view, named, private until shared). Drawn under the answer, only when its markers stand for
// any item. Its own file, mounted by `QuestionsPanel`'s answer in one line, so the panel's layout and these actions
// change apart.
import { useState } from "react";

import { currentBrand } from "../brand/brand";
import { SaveViewForm } from "../views/SaveViewForm";
import type { QuestionAnswer } from "./questionsApi";

export interface AnswerIds {
  nodeIds: string[];
  linkIds: string[];
}

/** Every item the answer's markers stand for, each once, in the order the markers give them: its graph facts, then
 * the records its search found. */
export function answerIds(entry: Pick<QuestionAnswer, "graph_citations" | "search_citations">): AnswerIds {
  const nodeIds = new Set<string>();
  const linkIds = new Set<string>();
  for (const fact of entry.graph_citations ?? []) {
    for (const id of fact.node_ids) nodeIds.add(id);
    for (const id of fact.link_ids) linkIds.add(id);
  }
  for (const source of entry.search_citations ?? []) for (const id of source.node_ids) nodeIds.add(id);
  return { nodeIds: [...nodeIds], linkIds: [...linkIds] };
}

/** The saved view's name the form offers: the question it answers, cut at a word if long. */
export function answerViewName(question: string): string {
  const words = question.trim().replace(/\s+/g, " ");
  const cut = words.length > 72 ? `${words.slice(0, 72).replace(/\s+\S*$/, "")}…` : words;
  return cut ? `Answer: ${cut}` : "Answer from Ask & Chat";
}

export interface AnswerActionsProps {
  entry: QuestionAnswer;
  /** Puts every item on the canvas and selects them. Absent: not offered. */
  onShowAll?: (ids: AnswerIds) => void;
  /** Saves the items as a saved view under `name`; answers `null` when saved, or the refusal in words. Absent: not
   * offered. */
  onSaveAsView?: (ids: AnswerIds, name: string) => Promise<string | null>;
}

export function AnswerActions({ entry, onShowAll, onSaveAsView }: AnswerActionsProps) {
  const [saving, setSaving] = useState(false);
  const ids = answerIds(entry);
  const govuk = currentBrand() === "govuk";
  if (ids.nodeIds.length === 0 && ids.linkIds.length === 0) return null;
  const canSave = onSaveAsView !== undefined && ids.nodeIds.length > 0;
  if (!onShowAll && !canSave) return null;
  const button = govuk ? "govuk-link answer-actions__link" : "btn";
  return (
    <div className="answer-actions" role="group" aria-label="This answer's items">
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)", alignItems: "center" }}>
        {onShowAll && (
          <button type="button" className={button} onClick={() => onShowAll(ids)}>
            Show all on graph
          </button>
        )}
        {canSave && (
          <button type="button" className={button} aria-expanded={saving} onClick={() => setSaving((open) => !open)}>
            Save as a view
          </button>
        )}
      </div>
      {saving && canSave && (
        <SaveViewForm
          count={ids.nodeIds.length}
          defaultName={answerViewName(entry.question)}
          onSave={async (name) => {
            const refused = await onSaveAsView(ids, name);
            if (refused === null) setSaving(false);
            return refused;
          }}
          onCancel={() => setSaving(false)}
        />
      )}
    </div>
  );
}
