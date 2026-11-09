// The top bar's *Needs you · n* (ADR-145 decision 11, A2; Amendment 4 decision 11, R7; ADR-090
// Amendment 4; L2.7): the proposed link types the reader may decide and the promotions overdue to
// them, each with a tip saying what it is and what follows. Everything it lists is what the Conduit
// served this reader (`GET /v1/me/needs-you`), so it lists nothing the reader cannot see. A proposal
// above their clearance is said to exist, and is neither counted nor described. The control is
// drawn only when something waits, or when the read failed (said, never shown as nothing, rule 2).
import { useCallback, useEffect, useState } from "react";

import { DropdownPanel } from "../../design/primitives/DropdownPanel";
import {
  NEEDS_YOU_WORDS as WORDS,
  needsYouCount,
  readNeedsYou,
  type NeedsYou as Needs,
} from "./needsYouApi";

export interface NeedsYouProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** Opens the Studio's Model tab on a dataset; without it, the entry is said but not a button. A
   * refusal (no case of theirs loads into it, their cases unread) is said beside the control. */
  onOpenModel?: (datasetId: string) => void | Promise<void>;
  /** Opens Admin › Operations, for a reader who holds `operate_schedules`. */
  onOpenOperations?: () => void;
  /** Read again when this changes (a decision on the Model tab, say). */
  generation?: number;
  /** How often to read again while open, in ms (default a minute). */
  every?: number;
  read?: (apiBaseUrl: string, bearerToken: string) => Promise<Needs>;
}

export function NeedsYou({
  apiBaseUrl,
  bearerToken,
  onOpenModel,
  onOpenOperations,
  generation = 0,
  every = 60_000,
  read = readNeedsYou,
}: NeedsYouProps) {
  const [needs, setNeeds] = useState<Needs | null>(null);
  const [failed, setFailed] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setNeeds(await read(apiBaseUrl, bearerToken));
      setFailed(false);
    } catch {
      setNeeds(null); // a count read earlier is not shown as if it still stood (rule 2)
      setFailed(true);
    }
  }, [apiBaseUrl, bearerToken, read]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), every);
    return () => window.clearInterval(timer);
  }, [load, every, generation]);

  const count = needs ? needsYouCount(needs) : 0;
  const hidden = needs ? needs.proposals.filter((p) => p.above_clearance) : [];
  if (!failed && !problem && count === 0 && hidden.length === 0) return null;
  const opening = (datasetId: string) => () => {
    setProblem(null);
    void Promise.resolve(onOpenModel?.(datasetId)).catch((e: unknown) =>
      setProblem(e instanceof Error ? e.message : "The Studio could not be opened on that dataset."),
    );
  };

  const entry = (
    key: string,
    words: string,
    tip: string,
    open?: () => void,
    close?: () => void,
  ) => {
    const tipId = `needs-you-tip-${key}`;
    return (
      <li key={key} className="needs-you__entry">
        {open ? (
          <button
            type="button"
            className="menu-panel__item"
            aria-describedby={tipId}
            onClick={() => {
              close?.();
              open();
            }}
          >
            {words}
          </button>
        ) : (
          <span
            className="needs-you__words"
            aria-describedby={tipId}
            tabIndex={0}
          >
            {words}
          </span>
        )}
        <span id={tipId} role="note" className="caption needs-you__tip">
          {tip}
        </span>
      </li>
    );
  };

  return (
    <>
    {problem && (
      <span role="alert" className="caption">
        {problem}
      </span>
    )}
    <DropdownPanel
      label={failed && !needs ? "Needs you · ?" : `Needs you · ${count}`}
      panelLabel="Needs you"
      alignRight
      buttonClassName="needs-you__button"
    >
      {(close) => (
        <ul
          className="needs-you"
          style={{
            listStyle: "none",
            margin: 0,
            padding: "var(--sp-8)",
            display: "grid",
            gap: "var(--sp-8)",
            maxWidth: 360,
          }}
        >
          {failed && <li role="alert">{WORDS.unread}</li>}
          {needs?.promotions_overdue.map((p) =>
            entry(
              `promotion-${p.promotion_id}`,
              p.words,
              WORDS.promotionTip,
              onOpenOperations,
              close,
            ),
          )}
          {needs?.proposals
            .filter((p) => p.to_decide > 0)
            .map((p) =>
              entry(
                `proposals-${p.dataset_id}`,
                WORDS.proposals(p.to_decide, p.dataset_name),
                WORDS.proposalsTip,
                onOpenModel ? opening(p.dataset_id) : undefined,
                close,
              ),
            )}
          {hidden.map((p) =>
            entry(
              `above-${p.dataset_id}`,
              WORDS.aboveClearance(p.dataset_name),
              WORDS.aboveClearanceTip,
            ),
          )}
        </ul>
      )}
    </DropdownPanel>
    </>
  );
}
