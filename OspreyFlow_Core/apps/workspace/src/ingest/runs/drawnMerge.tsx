// Ingest Studio › 4 Runs › *Merge into a dataset…* (ADR-143 Amendment 2 decisions 6 and 7; Amendment
// 3 decision 2): a drawn dataset merged into a dataset the reader is an Author of, in four steps.
//   1 Map the models: each drawn type and the target type its items go in as, or why not.
//   2 Match: the *Looks like a loaded item* pairs; each chosen one goes in as a proposed match
//     (inferred, scored) that a person confirms later; nothing is collapsed.
//   3 Dry run: what would be added and matched; nothing written.
//   4 Merge: one load into the target, under its promotion policy, listed with its promotions.
// It is drawn only for a drawn dataset the reader may merge; it decides nothing, and a step that
// cannot be taken says why. Built in `ingest/runs/` by agreement with the Studio lane.
import { useCallback, useEffect, useRef, useState } from "react";

import { ChecksList, LeftOutList, SheetChecklist } from "../../boards/PromoteSheet";
import { addsInWords, startingTicks, STATUS_WORDS, type Promotion } from "../../boards/promotionsApi";
import { currentBrand } from "../../brand/brand";
import {
  drawnMergeSheet,
  dryRunDrawnMerge,
  mergeDrawn,
  mergeTargets,
  type DrawnMergeDryRun,
  type DrawnMergeSheet,
  type MergeBody,
  type MergeTargets,
} from "./drawnMergeApi";

export interface DrawnMergeProps {
  apiBaseUrl: string;
  bearerToken: string;
  datasetId: string;
  /** Told when a merge is sent, so the Runs tab reads its promotions again. */
  onChanged?: () => void | Promise<void>;
}

const pairKey = (drawn: string, loaded: string) => JSON.stringify([drawn, loaded]);

export function DrawnMerge({ apiBaseUrl, bearerToken, datasetId, onChanged }: DrawnMergeProps) {
  const govuk = currentBrand() === "govuk";
  const [targets, setTargets] = useState<MergeTargets | null>(null);
  const [target, setTarget] = useState("");
  const [sheet, setSheet] = useState<DrawnMergeSheet | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [pairs, setPairs] = useState<Set<string>>(new Set());
  const [dry, setDry] = useState<DrawnMergeDryRun | null>(null);
  const [sent, setSent] = useState<Promotion | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  const reload = useCallback(async () => {
    const answer = await mergeTargets(apiBaseUrl, bearerToken, datasetId);
    // Not a drawn dataset, or one this reader may not merge: the panel is not drawn.
    setTargets(answer.ok ? answer.value : null);
  }, [apiBaseUrl, bearerToken, datasetId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (sheet) heading.current?.focus();
  }, [sheet, sent]);

  if (!targets) return null;

  async function open(): Promise<void> {
    setProblem(null);
    setSent(null);
    setDry(null);
    const answer = await drawnMergeSheet(apiBaseUrl, bearerToken, datasetId, target);
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    setSheet(answer.value);
    setTicked(startingTicks(answer.value.items ?? []));
    setPairs(new Set());
  }

  const body = (): MergeBody => ({
    target_dataset_id: target,
    item_ids: [...ticked],
    matches: [...pairs].map((p) => {
      const [drawn, loaded] = JSON.parse(p) as [string, string];
      return { drawn, loaded };
    }),
  });

  async function dryRun(): Promise<void> {
    setProblem(null);
    const answer = await dryRunDrawnMerge(apiBaseUrl, bearerToken, datasetId, body());
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    setDry(answer.value);
  }

  async function merge(): Promise<void> {
    setProblem(null);
    const answer = await mergeDrawn(apiBaseUrl, bearerToken, datasetId, body());
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    setSent(answer.value);
    await reload();
    await onChanged?.();
  }

  function close(): void {
    setSheet(null);
    setDry(null);
    setSent(null);
  }

  // Any change after the dry run asks for it again: what is merged is what was shown.
  const changed = () => setDry(null);
  const toggle = (itemId: string) => {
    changed();
    setTicked((held) => {
      const next = new Set(held);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  };
  const togglePair = (key: string) => {
    changed();
    setPairs((held) => {
      const next = new Set(held);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const button = govuk ? "govuk-button board__button" : "btn btn--primary board__button";
  const secondary = govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button";
  const cell = govuk ? "govuk-table__cell" : undefined;
  const header = govuk ? "govuk-table__header" : undefined;

  return (
    <section aria-labelledby="drawn-merge-title" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 id="drawn-merge-title" className={govuk ? "govuk-heading-s" : undefined} style={govuk ? undefined : { margin: 0, fontSize: "var(--fs-14)" }}>
        Merge into a dataset…
      </h3>
      <p className="label" style={{ margin: 0 }}>
        {targets.drawn_name} is a drawing that is its own dataset. As an Author of another dataset who may merge datasets, you may merge it
        into that one as one load. Afterwards its case reads that dataset, and the drawing becomes a view with its notes.
      </p>
      {targets.refused ? (
        <p className="label">{targets.refused}</p>
      ) : targets.targets.length === 0 ? (
        <p className="label">There is no dataset you may merge it into: you must be one of a dataset&apos;s Authors, in this drawing&apos;s unit.</p>
      ) : (
        <div className="board__row">
          <label htmlFor="drawn-merge-target" className={govuk ? "govuk-label" : "label"}>
            Merge into
          </label>{" "}
          <select
            id="drawn-merge-target"
            className={govuk ? "govuk-select" : "select"}
            value={target}
            onChange={(e) => {
              setTarget(e.target.value);
              close();
            }}
          >
            <option value="">Choose a dataset</option>
            {targets.targets.map((t) => (
              <option key={t.dataset_id} value={t.dataset_id}>
                {t.name}
              </option>
            ))}
          </select>{" "}
          <button type="button" className={secondary} disabled={!target} onClick={() => void open()}>
            Map and match
          </button>
        </div>
      )}
      {problem && (
        <div className={govuk ? "govuk-error-summary" : "board__problem-box"} role="alert">
          {govuk && <h4 className="govuk-error-summary__title">There is a problem</h4>}
          <p className={govuk ? "govuk-error-summary__body" : "board__problem"}>{problem}</p>
        </div>
      )}
      {sheet && (
        <section
          role="dialog"
          aria-labelledby="drawn-merge-sheet-title"
          className={govuk ? "board__panel" : "board__panel panel"}
          onKeyDown={(e) => {
            if (e.key === "Escape") close();
          }}
        >
          <h4 id="drawn-merge-sheet-title" ref={heading} tabIndex={-1} className={govuk ? "govuk-heading-s" : "label"}>
            {sent ? "Merge sent" : `Merge ${sheet.drawn_name} into ${sheet.target_name}`}
          </h4>
          {sent ? (
            <>
              <p className={govuk ? "govuk-body" : undefined}>
                <strong className={govuk ? "govuk-tag" : "board-tag"}>{STATUS_WORDS[sent.status]}</strong> {addsInWords(sent)}, load {sent.load_id}.
              </p>
              <LeftOutList promotion={sent} govuk={govuk} />
            </>
          ) : (
            <>
              <h5 className={govuk ? "govuk-heading-s" : "label"}>1. Map the models</h5>
              <table className={govuk ? "govuk-table" : "table"} aria-label="How each drawn type goes in">
                <thead className={govuk ? "govuk-table__head" : undefined}>
                  <tr className={govuk ? "govuk-table__row" : undefined}>
                    <th scope="col" className={header}>Drawn type</th>
                    <th scope="col" className={header}>Goes in as</th>
                    <th scope="col" className={header}>Items</th>
                  </tr>
                </thead>
                <tbody className={govuk ? "govuk-table__body" : undefined}>
                  {(sheet.mapping ?? []).map((m) => (
                    <tr key={`${m.kind} ${m.drawn_type}`} className={govuk ? "govuk-table__row" : undefined}>
                      <th scope="row" className={header} style={{ fontWeight: "normal", textAlign: "left" }}>
                        {m.drawn_type} ({m.kind === "node" ? "item" : "link"})
                      </th>
                      <td className={cell}>{m.target_type ?? m.why_not}</td>
                      <td className={cell}>{m.items}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h5 className={govuk ? "govuk-heading-s" : "label"}>2. Match</h5>
              {(sheet.matches ?? []).length === 0 ? (
                <p className="label">Nothing drawn looks like an item already loaded in {sheet.target_name} that you may see.</p>
              ) : (
                <fieldset className={govuk ? "govuk-fieldset" : undefined} style={{ border: govuk ? undefined : 0, padding: 0, margin: 0 }}>
                  <legend className={govuk ? "govuk-fieldset__legend" : "label"}>
                    Each one you tick is proposed as the same, for a person to confirm later; neither item is changed.
                  </legend>
                  <div className={govuk ? "govuk-checkboxes govuk-checkboxes--small" : undefined}>
                    {(sheet.matches ?? []).map((m) => {
                      const key = pairKey(m.drawn, m.loaded);
                      const id = `drawn-merge-match-${m.drawn}-${m.loaded}`;
                      return (
                        <div key={key} className={govuk ? "govuk-checkboxes__item" : "board__check"}>
                          <input id={id} type="checkbox" className={govuk ? "govuk-checkboxes__input" : undefined} checked={pairs.has(key)} onChange={() => togglePair(key)} />{" "}
                          <label htmlFor={id} className={govuk ? "govuk-label govuk-checkboxes__label" : undefined}>
                            {m.drawn_label} looks like {m.loaded_label} ({m.loaded_type}): {m.why}, {Math.round(m.score * 100)}%
                          </label>
                        </div>
                      );
                    })}
                  </div>
                  {sheet.more_matches && <p className="caption">More may be offered once these are decided.</p>}
                </fieldset>
              )}
              <h5 className={govuk ? "govuk-heading-s" : "label"}>What goes</h5>
              <SheetChecklist items={sheet.items ?? []} ticked={ticked} govuk={govuk} idPrefix="drawn-merge" onToggle={toggle} />
              <ChecksList sheet={sheet} govuk={govuk} />
              <h5 className={govuk ? "govuk-heading-s" : "label"}>3. Dry run</h5>
              {dry ? (
                <div role="status">
                  <p className={govuk ? "govuk-body" : undefined}>
                    It would add {dry.nodes} item{dry.nodes === 1 ? "" : "s"} and {dry.links} link{dry.links === 1 ? "" : "s"} to {sheet.target_name}, and propose{" "}
                    {dry.matches} match{dry.matches === 1 ? "" : "es"}. Nothing has been written.
                  </p>
                  {(dry.left_out ?? []).length > 0 && (
                    <ul className={govuk ? "govuk-list" : undefined}>
                      {(dry.left_out ?? []).map((l) => (
                        <li key={l.item_id}>
                          {l.label}: {l.why}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : (
                <p className="label">Run the dry run to see what the merge would do before you merge.</p>
              )}
            </>
          )}
          <div className="board__row">
            {!sent && (
              <button type="button" className={secondary} disabled={ticked.size === 0} onClick={() => void dryRun()}>
                Dry run
              </button>
            )}
            {!sent && (
              <button type="button" className={button} disabled={!dry} onClick={() => void merge()}>
                {sheet.policy === "author_promotes" ? "4. Merge" : "4. Send for review"}
              </button>
            )}
            {!sent && !dry && <span className="caption">Merge waits for the dry run.</span>}
            <button type="button" className={secondary} onClick={close}>
              {sent ? "Close" : "Cancel"}
            </button>
          </div>
        </section>
      )}
    </section>
  );
}
