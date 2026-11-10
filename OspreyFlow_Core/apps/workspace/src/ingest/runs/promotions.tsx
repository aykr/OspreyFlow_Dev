// Ingest Studio › 4 Runs › *Analyst promotions* (ADR-143 decision 10, C9; Amendment 2 decision 1).
// Every promotion into this dataset: the load, what it adds, who, the case, its status; *Details*;
// the revert command for a holder of `revert_loads`; and, when the dataset asks for a second person,
// *Review* → *Approve and commit* or *Reject with a reason*. Below it, a removed case's layer, for
// the dataset's Authors: *Merge into the dataset* (a read grant for that merge alone, opened by the
// sheet and closed with it) or *Delete* (promoted items never touched).
//
// It decides nothing. Who may review, and what a reviewer may read, are the Conduit's answers; an
// action a person cannot take says why, never only greyed out (ADR-145 Amendment 4 decision 12).
// Built in `ingest/runs/promotions*` by agreement with the Studio lane (the parallel build plan's
// ownership map).
import { useCallback, useEffect, useRef, useState } from "react";

import { ChecksList, LeftOutList, SheetChecklist } from "../../boards/PromoteSheet";
import {
  addsInWords,
  startingTicks,
  STATUS_WORDS,
  type LayerMergeSheet,
  type Promotion,
  type PromotionDetails,
  type RemovedCaseLayers,
} from "../../boards/promotionsApi";
import {
  cancelLayerMerge,
  datasetPromotions,
  decidePromotion,
  deleteLayer,
  dryRunDeleteLayer,
  mergeLayer,
  openLayerMerge,
  promotionDetails,
  removedCases,
} from "./promotionsApi";
import { currentBrand } from "../../brand/brand";

const TAG: Record<Promotion["status"], string> = {
  awaiting_review: "govuk-tag--yellow",
  committed: "govuk-tag--green",
  rejected: "govuk-tag--red",
  reverted: "govuk-tag--grey",
};

/** The operator's command, as `scripts/revert_promotion.py` takes it. */
export function promotionRevertCommand(loadId: string, username: string | null): string {
  return `python -m scripts.revert_promotion ${loadId} --reverted-by ${username || "<your username>"}`;
}

export interface AnalystPromotionsProps {
  apiBaseUrl: string;
  bearerToken: string;
  datasetId: string;
  canRevert: boolean;
  username: string | null;
}

export function AnalystPromotions({ apiBaseUrl, bearerToken, datasetId, canRevert, username }: AnalystPromotionsProps) {
  const govuk = currentBrand() === "govuk";
  const [promotions, setPromotions] = useState<Promotion[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [open, setOpen] = useState<PromotionDetails | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [said, setSaid] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);

  const reload = useCallback(async () => {
    const answer = await datasetPromotions(apiBaseUrl, bearerToken, datasetId);
    if (answer.ok) {
      setPromotions(answer.value.promotions ?? []);
      setRefused(null);
    } else {
      setPromotions(null);
      setRefused(
        answer.code === "right_required" || answer.code === "forbidden"
          ? "You need Review promotions to see the analyst promotions into this dataset; a data engineer of the dataset has it."
          : answer.message,
      );
    }
  }, [apiBaseUrl, bearerToken, datasetId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Into a promotion's details once they are drawn.
  useEffect(() => {
    if (open) heading.current?.focus();
  }, [open]);

  async function details(p: Promotion): Promise<void> {
    setProblem(null);
    setRejecting(false);
    setReason("");
    const answer = await promotionDetails(apiBaseUrl, bearerToken, datasetId, p.id);
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    setOpen(answer.value);
  }

  async function decide(approve: boolean): Promise<void> {
    if (!open) return;
    setProblem(null);
    const answer = await decidePromotion(apiBaseUrl, bearerToken, datasetId, open.promotion.id, approve, approve ? undefined : reason.trim());
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    setSaid(approve ? `Approved and committed: load ${answer.value.load_id}.` : `Rejected: load ${answer.value.load_id}.`);
    setOpen(null);
    await reload();
  }

  return (
    <section aria-labelledby="analyst-promotions-title" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 id="analyst-promotions-title" className={govuk ? "govuk-heading-s" : undefined} style={govuk ? undefined : { margin: 0, fontSize: "var(--fs-14)" }}>
        Analyst promotions
      </h3>
      <p className="label" style={{ margin: 0 }}>
        Drawn items promoted from a case&apos;s board into this dataset, each as one load. Under Second person reviews, one of the
        dataset&apos;s Authors who may review promotions approves or rejects it here; never the person who sent it.
      </p>
      {refused && <p className="label">{refused}</p>}
      {promotions && promotions.length === 0 && <p className="label">No analyst promotion into this dataset yet.</p>}
      {promotions && promotions.length > 0 && (
        <table className={govuk ? "govuk-table" : "table"}>
          <thead className={govuk ? "govuk-table__head" : undefined}>
            <tr className={govuk ? "govuk-table__row" : undefined}>
              {["Load", "What it adds", "Who", "Case", "Status", ""].map((h) => (
                <th key={h || "actions"} scope="col" className={govuk ? "govuk-table__header" : undefined}>
                  {h || <span className="visually-hidden">Actions</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className={govuk ? "govuk-table__body" : undefined}>
            {promotions.map((p) => (
              <tr key={p.id} className={govuk ? "govuk-table__row" : undefined}>
                <td className={govuk ? "govuk-table__cell" : undefined}>
                  <code style={{ overflowWrap: "anywhere" }}>{p.load_id}</code>
                  {p.trigger === "layer_merge" && <span className="label"> · a removed case&apos;s layer</span>}
                </td>
                <td className={govuk ? "govuk-table__cell" : undefined}>{addsInWords(p)}</td>
                <td className={govuk ? "govuk-table__cell" : undefined}>
                  {p.proposed_by_name}, {new Date(p.proposed_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
                </td>
                <td className={govuk ? "govuk-table__cell" : undefined}>{p.case_name}</td>
                <td className={govuk ? "govuk-table__cell" : undefined}>
                  <strong className={govuk ? `govuk-tag ${TAG[p.status]}` : "board-tag"}>{STATUS_WORDS[p.status]}</strong>
                  {p.reviewed_by_name && <span className="label">{` by ${p.reviewed_by_name}`}</span>}
                  {p.reason && <span className="label">{` — ${p.reason}`}</span>}
                </td>
                <td className={govuk ? "govuk-table__cell" : undefined}>
                  <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={() => void details(p)}>
                    {p.may_review ? "Review" : "Details"}
                    <span className="visually-hidden">{` load ${p.load_id}`}</span>
                  </button>
                  {p.status === "awaiting_review" && !p.may_review && p.why_not && <p className="label" style={{ margin: 0 }}>{p.why_not}</p>}
                  {canRevert && p.revert_command && (
                    <div>
                      <span className="label">Revert it, from OspreyFlow_Core, with the Conduit stopped:</span>
                      <code style={{ display: "block", overflowWrap: "anywhere" }}>{promotionRevertCommand(p.load_id, username)}</code>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {problem && (
        <div className={govuk ? "govuk-error-summary" : "board__problem-box"} role="alert">
          {govuk && <h4 className="govuk-error-summary__title">There is a problem</h4>}
          <p className={govuk ? "govuk-error-summary__body" : "board__problem"}>{problem}</p>
        </div>
      )}
      {open && (
        <section
          role="dialog"
          aria-labelledby="promotion-details-title"
          className={govuk ? "board__panel" : "board__panel panel"}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(null);
          }}
        >
          <h4 id="promotion-details-title" ref={heading} tabIndex={-1} className={govuk ? "govuk-heading-s" : "label"}>
            Load {open.promotion.load_id}: {addsInWords(open.promotion)} from {open.promotion.case_name}
          </h4>
          {open.withheld && (
            <p className={govuk ? "govuk-inset-text" : "label"}>Some of its items are not shown to you, so you may not approve it.</p>
          )}
          <dl className={govuk ? "govuk-summary-list" : "board__summary"}>
            {open.items.map((i) => (
              <div key={i.element_id} className={govuk ? "govuk-summary-list__row" : "board__summary-row"}>
                <dt className={govuk ? "govuk-summary-list__key" : "label"}>{i.label}</dt>
                <dd className={govuk ? "govuk-summary-list__value" : undefined}>
                  {i.type}
                  {i.goes_in_as ? ` (goes in as a new ${i.goes_in_as})` : ""}, {i.marking}
                  {i.grading ? `, graded ${i.grading}` : ""}
                  {i.source_note ? ` — ${i.source_note}` : ""}
                </dd>
              </div>
            ))}
          </dl>
          {/* A drawn dataset's merge (L3.9): the matches it proposes are approved with it, so the
              reviewer reads each, as the Conduit gives it to them. */}
          {(open.matches ?? []).length > 0 && (
            <>
              <h5 className={govuk ? "govuk-heading-s" : "label"}>Proposed as the same, for a person to confirm later</h5>
              <ul className={govuk ? "govuk-list" : undefined} aria-label="Proposed matches">
                {(open.matches ?? []).map((m) => (
                  <li key={`${m.drawn} ${m.loaded}`}>
                    {m.drawn_label} and {m.loaded_label} ({m.loaded_type}), {Math.round(m.score * 100)}%
                  </li>
                ))}
              </ul>
            </>
          )}
          <LeftOutList promotion={open.promotion} govuk={govuk} />
          {open.promotion.may_review && !rejecting && (
            <div className="board__row">
              <button type="button" className={govuk ? "govuk-button board__button" : "btn btn--primary board__button"} disabled={open.withheld} onClick={() => void decide(true)}>
                Approve and commit
              </button>
              <button type="button" className={govuk ? "govuk-button govuk-button--warning board__button" : "btn board__button"} onClick={() => setRejecting(true)}>
                Reject with a reason
              </button>
            </div>
          )}
          {rejecting && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (reason.trim()) void decide(false);
                else setProblem("Say why it is rejected: the analyst sees the reason on their board.");
              }}
              style={{ display: "grid", gap: "var(--sp-6)" }}
            >
              <label htmlFor="promotion-reject-reason" className={govuk ? "govuk-label" : "label"}>
                Why it is rejected
              </label>
              <textarea
                id="promotion-reject-reason"
                className={govuk ? "govuk-textarea" : "input board__textarea"}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <div className="board__row">
                <button type="submit" className={govuk ? "govuk-button govuk-button--warning board__button" : "btn board__button"}>
                  Reject
                </button>
                <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={() => setRejecting(false)}>
                  Keep it waiting
                </button>
              </div>
            </form>
          )}
          <div className="board__row">
            <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={() => setOpen(null)}>
              Close
            </button>
          </div>
        </section>
      )}
      <RemovedCaseLayersPanel apiBaseUrl={apiBaseUrl} bearerToken={bearerToken} datasetId={datasetId} govuk={govuk} onChanged={reload} onSaid={setSaid} />
      <p className="visually-hidden" role="status" aria-live="polite">
        {said}
      </p>
    </section>
  );
}

function RemovedCaseLayersPanel({
  apiBaseUrl,
  bearerToken,
  datasetId,
  govuk,
  onChanged,
  onSaid,
}: {
  apiBaseUrl: string;
  bearerToken: string;
  datasetId: string;
  govuk: boolean;
  onChanged: () => Promise<void>;
  onSaid: (words: string) => void;
}) {
  const [layers, setLayers] = useState<RemovedCaseLayers | null>(null);
  const [sheet, setSheet] = useState<LayerMergeSheet | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState<{ caseId: string; would: string } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [merged, setMerged] = useState<Promotion | null>(null);
  const sheetHeading = useRef<HTMLHeadingElement>(null);

  const reload = useCallback(async () => {
    const answer = await removedCases(apiBaseUrl, bearerToken, datasetId);
    // Only the dataset's Authors are answered; for anyone else the panel is not drawn.
    setLayers(answer.ok ? answer.value : null);
  }, [apiBaseUrl, bearerToken, datasetId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Into the sheet once it is drawn, and onto its outcome once sent.
  useEffect(() => {
    if (sheet) sheetHeading.current?.focus();
  }, [sheet, merged]);

  if (!layers || layers.cases.length === 0) return null;

  async function openMerge(caseId: string): Promise<void> {
    setProblem(null);
    setMerged(null);
    const answer = await openLayerMerge(apiBaseUrl, bearerToken, datasetId, caseId);
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    setSheet(answer.value);
    setTicked(startingTicks(answer.value.items ?? []));
  }

  async function closeMerge(): Promise<void> {
    if (sheet && !merged) await cancelLayerMerge(apiBaseUrl, bearerToken, datasetId, sheet.grant_id);
    setSheet(null);
    setMerged(null);
  }

  async function merge(): Promise<void> {
    if (!sheet) return;
    const answer = await mergeLayer(apiBaseUrl, bearerToken, datasetId, sheet.grant_id, [...ticked]);
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    setMerged(answer.value);
    onSaid(`Merged from ${sheet.case_name}: ${STATUS_WORDS[answer.value.status]}.`);
    await reload();
    await onChanged();
  }

  async function askToDelete(caseId: string): Promise<void> {
    setProblem(null);
    // The dry run first, as Amendment 2 decision 1 asks: what would go, and nothing written.
    const answer = await dryRunDeleteLayer(apiBaseUrl, bearerToken, datasetId, caseId);
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    setDeleting({ caseId, would: answer.value.would });
  }

  async function remove(caseId: string, name: string): Promise<void> {
    const answer = await deleteLayer(apiBaseUrl, bearerToken, datasetId, caseId);
    setDeleting(null);
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    onSaid(`${name}: ${answer.value.words}`);
    await reload();
  }

  const toggle = (itemId: string) =>
    setTicked((held) => {
      const next = new Set(held);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });

  return (
    <section aria-labelledby="removed-layers-title" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 id="removed-layers-title" className={govuk ? "govuk-heading-s" : undefined} style={govuk ? undefined : { margin: 0, fontSize: "var(--fs-14)" }}>
        Removed cases&apos; layers
      </h3>
      <p className="label" style={{ margin: 0 }}>
        What analysts drew in a case that has been removed, kept read-only. As one of this dataset&apos;s Authors you may merge it into the
        dataset, as a promotion, or delete it. Nothing deletes a layer on its own.
      </p>
      <ul className={govuk ? "govuk-list" : undefined} style={{ margin: 0, paddingLeft: govuk ? undefined : "var(--sp-16)", display: "grid", gap: "var(--sp-6)" }}>
        {layers.cases.map((c) => (
          <li key={c.investigation_id}>
            {c.name}: {c.items} item{c.items === 1 ? "" : "s"}{" "}
            {c.mergeable ? (
              <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={() => void openMerge(c.investigation_id)}>
                Merge into the dataset<span className="visually-hidden">{` from ${c.name}`}</span>
              </button>
            ) : (
              <span className="label">{c.why_not}</span>
            )}{" "}
            {deleting?.caseId === c.investigation_id ? (
              <span role="group" aria-label={`Delete ${c.name}'s layer?`}>
                <span className="label">
                  {deleting.would} Delete it? Its items are withdrawn and kept in the audit.
                </span>{" "}
                <button type="button" className={govuk ? "govuk-button govuk-button--warning board__button" : "btn btn--danger board__button"} onClick={() => void remove(c.investigation_id, c.name)}>
                  Delete the layer
                </button>{" "}
                <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={() => setDeleting(null)}>
                  Keep it
                </button>
              </span>
            ) : (
              <button type="button" className={govuk ? "govuk-button govuk-button--warning board__button" : "btn board__button"} onClick={() => void askToDelete(c.investigation_id)}>
                Delete…<span className="visually-hidden">{` ${c.name}'s layer`}</span>
              </button>
            )}
          </li>
        ))}
      </ul>
      {problem && (
        <div className={govuk ? "govuk-error-summary" : "board__problem-box"} role="alert">
          {govuk && <h4 className="govuk-error-summary__title">There is a problem</h4>}
          <p className={govuk ? "govuk-error-summary__body" : "board__problem"}>{problem}</p>
        </div>
      )}
      {sheet && (
        <section
          role="dialog"
          aria-labelledby="layer-merge-title"
          className={govuk ? "board__panel" : "board__panel panel"}
          onKeyDown={(e) => {
            if (e.key === "Escape") void closeMerge();
          }}
        >
          <h4 id="layer-merge-title" ref={sheetHeading} tabIndex={-1} className={govuk ? "govuk-heading-s" : "label"}>
            {merged ? "Merge sent" : `Merge ${sheet.case_name}'s layer into ${sheet.dataset_name}`}
          </h4>
          {merged ? (
            <>
              <p className={govuk ? "govuk-body" : undefined}>
                <strong className={govuk ? `govuk-tag ${TAG[merged.status]}` : "board-tag"}>{STATUS_WORDS[merged.status]}</strong> {addsInWords(merged)}, load{" "}
                {merged.load_id}.
              </p>
              <LeftOutList promotion={merged} govuk={govuk} />
            </>
          ) : (
            <>
              <p className="caption">
                Opening this sheet let you read this one layer, for this merge alone; it is recorded in the audit and ends when the merge
                closes.
              </p>
              <SheetChecklist items={sheet.items ?? []} ticked={ticked} govuk={govuk} idPrefix="merge" onToggle={toggle} />
              <ChecksList sheet={sheet} govuk={govuk} />
            </>
          )}
          <div className="board__row">
            {!merged && (
              <button type="button" className={govuk ? "govuk-button board__button" : "btn btn--primary board__button"} disabled={ticked.size === 0} onClick={() => void merge()}>
                {sheet.policy === "author_promotes" ? "Merge" : "Send for review"}
              </button>
            )}
            <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={() => void closeMerge()}>
              {merged ? "Close" : "Cancel"}
            </button>
          </div>
        </section>
      )}
    </section>
  );
}
