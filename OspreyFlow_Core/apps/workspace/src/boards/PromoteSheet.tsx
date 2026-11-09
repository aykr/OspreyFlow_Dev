// *Promote…* (ADR-143 decision 8): the board's drawn items not yet promoted, each ticked or not;
// the checks; undecided matches as warnings; how it will be recorded. An item failing a check
// cannot be ticked, and says why; a link, picture or match decision follows its items. Everything
// that does not go is listed afterwards with its reason (rule 2). Under the GOV.UK brand the lists
// are a summary list and the ticks GOV.UK checkboxes (decision 13).
//
// The checks shown are the Conduit's, and it runs them again when the promotion is sent: nothing
// here decides what may go.
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { addsInWords, promote, promotionSheet, startingTicks, STATUS_WORDS, type Promotion, type PromotionSheet, type SheetItem } from "./promotionsApi";

const KIND_WORDS: Record<SheetItem["kind"], string> = { node: "Item", link: "Link", picture: "Picture", match: "Match decision" };

export function SheetChecklist({
  items,
  ticked,
  govuk,
  idPrefix,
  onToggle,
}: {
  items: readonly SheetItem[];
  ticked: ReadonlySet<string>;
  govuk: boolean;
  idPrefix: string;
  onToggle: (itemId: string) => void;
}) {
  if (items.length === 0) return <p className="caption">Nothing here is waiting to be promoted.</p>;
  return (
    <fieldset className={govuk ? "govuk-fieldset" : "board__fieldset"}>
      <legend className={govuk ? "govuk-fieldset__legend govuk-fieldset__legend--s" : "label"}>What goes</legend>
      <div className={govuk ? "govuk-checkboxes govuk-checkboxes--small" : "board__checks"}>
        {items.map((item) => {
          const id = `${idPrefix}-${item.item_id}`;
          const problems = item.problems ?? [];
          return (
            <div key={item.item_id} className={govuk ? "govuk-checkboxes__item" : "board__check"}>
              <input
                id={id}
                type="checkbox"
                className={govuk ? "govuk-checkboxes__input" : undefined}
                checked={ticked.has(item.item_id)}
                disabled={problems.length > 0}
                aria-describedby={problems.length > 0 ? `${id}-why` : undefined}
                onChange={() => onToggle(item.item_id)}
              />
              <label htmlFor={id} className={govuk ? "govuk-label govuk-checkboxes__label" : undefined}>
                {KIND_WORDS[item.kind]}: {item.label} ({item.type}, {item.marking})
                {item.follows ? " — goes when its ends go" : ""}
              </label>
              {problems.length > 0 && (
                <p id={`${id}-why`} className={govuk ? "govuk-checkboxes__hint board__why" : "caption board__why"}>
                  Cannot go: {problems.join(" ")}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}

export function ChecksList({ sheet, govuk }: { sheet: Pick<PromotionSheet, "checks" | "warnings" | "recorded_as">; govuk: boolean }) {
  return (
    <>
      <dl className={govuk ? "govuk-summary-list govuk-summary-list--no-border" : "board__summary"}>
        {(sheet.checks ?? []).map((check) => (
          <div key={check.name} className={govuk ? "govuk-summary-list__row" : "board__summary-row"}>
            <dt className={govuk ? "govuk-summary-list__key" : "label"}>{check.passed ? "Passed" : "Not passed"}</dt>
            <dd className={govuk ? "govuk-summary-list__value" : undefined}>{check.words}</dd>
          </div>
        ))}
      </dl>
      {(sheet.warnings ?? []).length > 0 && (
        <ul className={govuk ? "govuk-list govuk-list--bullet" : "board__warnings"} aria-label="Warnings">
          {(sheet.warnings ?? []).map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      <p className="caption">{sheet.recorded_as}</p>
    </>
  );
}

export function LeftOutList({ promotion, govuk }: { promotion: Promotion; govuk: boolean }) {
  if ((promotion.left_out ?? []).length === 0) return null;
  return (
    <>
      <h4 className={govuk ? "govuk-heading-s" : "label"}>Left out, and why</h4>
      <dl className={govuk ? "govuk-summary-list" : "board__summary"}>
        {(promotion.left_out ?? []).map((l) => (
          <div key={l.item_id} className={govuk ? "govuk-summary-list__row" : "board__summary-row"}>
            <dt className={govuk ? "govuk-summary-list__key" : "label"}>{l.label}</dt>
            <dd className={govuk ? "govuk-summary-list__value" : undefined}>{l.why}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

export interface PromoteSheetProps {
  apiBaseUrl: string;
  bearerToken: string;
  caseId: string;
  boardId: string;
  govuk: boolean;
  onClose: () => void;
  onPromoted: (promotion: Promotion) => void;
}

export function PromoteSheet({ apiBaseUrl, bearerToken, caseId, boardId, govuk, onClose, onPromoted }: PromoteSheetProps) {
  const [sheet, setSheet] = useState<PromotionSheet | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [problem, setProblem] = useState<string | null>(null);
  const [done, setDone] = useState<Promotion | null>(null);
  const title = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    void promotionSheet(apiBaseUrl, bearerToken, caseId, boardId).then((answer) => {
      if (!answer.ok) setProblem(answer.message);
      else {
        setSheet(answer.value);
        setTicked(startingTicks(answer.value.items ?? []));
      }
    });
  }, [apiBaseUrl, bearerToken, caseId, boardId]);

  // Into the sheet once it is drawn, and onto the outcome once sent.
  useEffect(() => {
    if (sheet || problem) title.current?.focus();
  }, [sheet, done, problem]);

  const toggle = (itemId: string) =>
    setTicked((held) => {
      const next = new Set(held);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });

  async function send(): Promise<void> {
    setProblem(null);
    const answer = await promote(apiBaseUrl, bearerToken, caseId, boardId, [...ticked]);
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    setDone(answer.value);
    onPromoted(answer.value);
  }

  const escape = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
    }
  };

  return (
    <section className={govuk ? "board__panel" : "board__panel panel"} role="dialog" aria-labelledby="promote-title" onKeyDown={escape}>
      <h3 id="promote-title" ref={title} tabIndex={-1} className={govuk ? "govuk-heading-s" : "label"}>
        {done ? "Promotion sent" : `Promote into ${sheet?.dataset_name ?? "the dataset"}`}
      </h3>
      {problem && (
        <div className={govuk ? "govuk-error-summary" : "board__problem-box"} role="alert">
          {govuk && <h4 className="govuk-error-summary__title">There is a problem</h4>}
          <p className={govuk ? "govuk-error-summary__body" : "board__problem"}>{problem}</p>
        </div>
      )}
      {done ? (
        <>
          <p className={govuk ? "govuk-body" : undefined}>
            <strong className={govuk ? "govuk-tag" : "board-tag"}>{STATUS_WORDS[done.status]}</strong> {addsInWords(done)} into {done.dataset_name}, load{" "}
            {done.load_id}.
            {done.status === "awaiting_review" ? " A second person reviews it in the Ingest Studio; nothing of it is in the dataset until then." : ""}
          </p>
          <LeftOutList promotion={done} govuk={govuk} />
        </>
      ) : sheet?.refused ? (
        <p className={govuk ? "govuk-body" : "caption"}>{sheet.refused}</p>
      ) : sheet ? (
        <>
          <p className="caption">
            Into {sheet.dataset_name}, marked no higher than {sheet.highest_marking};{" "}
            {sheet.policy === "author_promotes" ? "you promote it." : "a second person reviews it first."}
          </p>
          <SheetChecklist items={sheet.items ?? []} ticked={ticked} govuk={govuk} idPrefix="promote" onToggle={toggle} />
          <ChecksList sheet={sheet} govuk={govuk} />
        </>
      ) : (
        <p className="caption">Reading what can be promoted…</p>
      )}
      <div className="board__row">
        {!done && sheet && !sheet.refused && (
          <button type="button" className={govuk ? "govuk-button board__button" : "btn btn--primary board__button"} disabled={ticked.size === 0} onClick={() => void send()}>
            {sheet.policy === "author_promotes" ? "Promote" : "Send for review"}
          </button>
        )}
        <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={onClose}>
          {done ? "Close" : "Cancel"}
        </button>
      </div>
    </section>
  );
}

export function BoardPromotionsList({ promotions, govuk }: { promotions: readonly Promotion[]; govuk: boolean }) {
  return (
    <section className={govuk ? "board__panel" : "board__panel panel"} aria-labelledby="board-promotions-title">
      <h3 id="board-promotions-title" className={govuk ? "govuk-heading-s" : "label"}>
        Promotions from this board
      </h3>
      {promotions.length === 0 ? (
        <p className="caption">None yet.</p>
      ) : (
        <ul className={govuk ? "govuk-list" : "board__promotions"}>
          {promotions.map((p) => (
            <li key={p.id}>
              <strong className={govuk ? "govuk-tag govuk-tag--grey" : "board-tag"}>{STATUS_WORDS[p.status]}</strong> {addsInWords(p)} into {p.dataset_name},{" "}
              {new Date(p.proposed_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
              {p.reason ? ` — ${p.reason}` : ""}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
