// The Studio's *1 Model* tab's proposals block (ADR-143 decision 9, ADR-090 Amendment 4; L3.5): the link
// types analysts proposed in cases reading this dataset, each added to the dataset's draft domain model
// or declined, with a reason, by a holder of `accept_types`. Added, it is made live with the next model
// version and its links can then be promoted; declined, its links stay in their case's layer for good.
// The block never names the case a type was proposed in (rule 3). A person without `accept_types`, or a
// dataset they are not let into, is told nothing: the block is not drawn. Under the GOV.UK brand it is a
// summary list with status tags, GOV.UK buttons and a textarea with an error summary (ADR-143
// decision 13).
import { useCallback, useEffect, useRef, useState } from "react";

import { currentBrand } from "../brand/brand";
import { LinkTypeError, type ProposalStatus } from "./linkTypesApi";
import { decideModelProposal, listModelProposals, type ModelProposal } from "./modelProposalsApi";

export interface ModelProposalsProps {
  apiBaseUrl: string;
  bearerToken: string;
  datasetId: string;
  datasetName: string;
}

type Decision = "accept" | "decline";
type Basis = "" | "direct" | "probabilistic";

const STATUS: Partial<Record<ProposalStatus, { words: string; tag: string }>> = {
  pending: { words: "Proposed", tag: "govuk-tag--yellow" },
  rejected: { words: "Declined", tag: "govuk-tag--red" },
  withdrawn: { words: "Withdrawn", tag: "govuk-tag--grey" },
  merged: { words: "Merged", tag: "govuk-tag--grey" },
};

/** An accepted type's tag says where it stands in the dataset's model: live, in the draft, or lost
 * from the draft (discarded, or saved without it), when it may be added again. */
function statusOf(p: ModelProposal): { words: string; tag: string } {
  if (p.status === "accepted") {
    if (p.in_model === "live") return { words: "In the live model", tag: "govuk-tag--green" };
    if (p.in_model === "draft") return { words: "In the draft model", tag: "govuk-tag--blue" };
    return { words: "Accepted, not in the model", tag: "govuk-tag--orange" };
  }
  return STATUS[p.status] ?? { words: p.status, tag: "govuk-tag--grey" };
}

/** Pending, or accepted and lost from the model: still to decide. */
function decidable(p: ModelProposal): boolean {
  return p.status === "pending" || (p.status === "accepted" && !p.in_model);
}

export function title(p: ModelProposal): string {
  return p.label?.trim() || p.name;
}

export function ends(p: ModelProposal): string {
  const from = p.from_types.join(" or ");
  const to = p.to_types.join(" or ");
  return p.directed ? `${from} to ${to}, one way` : `${from} and ${to}, either way`;
}

function sentence(error: unknown): string {
  if (error instanceof LinkTypeError) {
    if (error.kind === "refused") return error.message;
    if (error.kind === "not_found") return "That proposal is no longer there to decide.";
    if (error.kind === "model_refused") return error.message;
    if (error.kind === "forbidden") return "Deciding proposed types needs the right to accept types.";
  }
  return "Nothing was decided; try again.";
}

export function ModelProposals({ apiBaseUrl, bearerToken, datasetId, datasetName }: ModelProposalsProps) {
  const govuk = currentBrand() === "govuk";
  const [proposals, setProposals] = useState<ModelProposal[] | null>(null);
  const [hidden, setHidden] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [deciding, setDeciding] = useState<{ id: string; decision: Decision } | null>(null);
  const [reason, setReason] = useState("");
  const [basis, setBasis] = useState<Basis>("");
  const [problem, setProblem] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // The button that opened the form is not drawn while the form is, so focus goes back to it by its
  // text once it is drawn again (Escape or Cancel).
  const [refocus, setRefocus] = useState<string | null>(null);
  const section = useRef<HTMLElement | null>(null);
  const openedBy = useRef<string | null>(null);
  const outcome = useRef<HTMLParagraphElement | null>(null);

  const load = useCallback(async () => {
    try {
      setProposals(await listModelProposals(apiBaseUrl, bearerToken, datasetId));
      setLoadFailed(false);
      setHidden(false);
    } catch (error) {
      // Not this person's to decide, or not their dataset: the block is not drawn at all.
      if (error instanceof LinkTypeError && (error.kind === "forbidden" || error.kind === "not_found")) setHidden(true);
      else setLoadFailed(true);
    }
  }, [apiBaseUrl, bearerToken, datasetId]);

  useEffect(() => {
    setDeciding(null);
    setDone(null);
    void load();
  }, [load]);

  useEffect(() => {
    if (refocus === null) return;
    const back = [...(section.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])].find(
      (b) => b.textContent === refocus,
    );
    back?.focus();
    setRefocus(null);
  }, [refocus]);

  // After a decision the form is gone: focus goes to what was done, not to the page.
  useEffect(() => {
    if (done) outcome.current?.focus();
  }, [done]);

  if (hidden) return null;

  const start = (id: string, decision: Decision, button: HTMLButtonElement) => {
    openedBy.current = button.textContent;
    setDeciding({ id, decision });
    setReason("");
    setBasis("");
    setProblem(null);
    setDone(null);
  };
  const cancel = () => {
    setDeciding(null);
    setProblem(null);
    setRefocus(openedBy.current);
  };
  const decide = async (proposal: ModelProposal) => {
    if (!deciding || busy) return;
    if (deciding.decision === "accept" && basis === "") {
      setProblem("Say what stands behind its links: Direct or Probabilistic.");
      return;
    }
    if (reason.trim() === "") {
      setProblem("Say why: a reason is required.");
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await decideModelProposal(apiBaseUrl, bearerToken, datasetId, proposal.id, deciding.decision, reason.trim(), basis || undefined);
      setDone(
        deciding.decision === "accept"
          ? `${title(proposal)} added to the draft model: its links can be promoted once that version is made live.`
          : `${title(proposal)} declined: its links stay in their case and are never promoted.`,
      );
      setDeciding(null);
      await load();
    } catch (error) {
      setProblem(sentence(error));
    } finally {
      setBusy(false);
    }
  };

  const pending = (proposals ?? []).filter(decidable).length;
  const button = (primary: boolean) =>
    govuk ? `govuk-button ${primary ? "" : "govuk-button--secondary"} model-proposals__button` : `btn ${primary ? "btn--primary" : ""}`;
  const muted = govuk ? "govuk-body-s" : "caption";

  return (
    <section ref={section} aria-labelledby="model-proposals-heading" className="model-proposals" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 id="model-proposals-heading" className={govuk ? "govuk-heading-s" : undefined} style={{ margin: 0, fontSize: govuk ? undefined : "var(--fs-14)" }}>
        Proposed link types{pending > 0 ? ` (${pending} to decide)` : ""}
      </h3>
      <p className={muted} style={{ margin: 0 }}>
        {`Analysts proposed these in cases reading ${datasetName}. Added to the draft model, a type is made live with the next model version, and its links can then be promoted into the dataset. Declined, its links stay in their case.`}
      </p>
      {loadFailed && (
        <p role="alert" className={govuk ? "govuk-error-message" : muted} style={{ margin: 0 }}>
          The proposed link types could not be read. Open the tab again to retry.
        </p>
      )}
      {done && (
        <p ref={outcome} tabIndex={-1} role="status" className={muted} style={{ margin: 0 }}>
          {done}
        </p>
      )}
      {proposals !== null && proposals.length === 0 && !loadFailed && (
        <p className={muted} style={{ margin: 0 }}>
          No link types have been proposed for this dataset.
        </p>
      )}
      {proposals !== null && proposals.length > 0 && (
        <dl className={govuk ? "govuk-summary-list" : "model-proposals__list"} aria-label="Proposed link types" style={{ margin: 0, display: govuk ? undefined : "grid", gap: "var(--sp-8)" }}>
          {proposals.map((p) => {
            const status = statusOf(p);
            const open = deciding?.id === p.id;
            return (
              <div key={p.id} className={govuk ? "govuk-summary-list__row" : undefined} data-proposal-id={p.id} style={govuk ? undefined : { borderBottom: "1px solid var(--border-subtle)", paddingBottom: "var(--sp-8)", display: "grid", gap: "var(--sp-4)" }}>
                <dt className={govuk ? "govuk-summary-list__key" : undefined} style={{ margin: 0 }}>
                  <strong>{title(p)}</strong> <span className={muted}>{p.name}</span>{" "}
                  <strong className={govuk ? `govuk-tag ${status.tag}` : muted}>{status.words}</strong>
                </dt>
                <dd className={govuk ? "govuk-summary-list__value" : undefined} style={{ margin: 0, display: "grid", gap: "var(--sp-4)" }}>
                  <span>{`What it means: “${p.reason}”`}</span>
                  <span className={muted}>{`${ends(p)}. Proposed by ${p.proposed_by} on ${p.proposed_at.slice(0, 10)}.`}</span>
                  {p.decision_reason && p.status !== "pending" && (
                    <span className={muted}>{`Decided by ${p.decided_by ?? "someone"}: “${p.decision_reason}”`}</span>
                  )}
                  {open && deciding && (
                    <DecisionForm
                      govuk={govuk}
                      proposal={p}
                      decision={deciding.decision}
                      reason={reason}
                      basis={basis}
                      onBasis={setBasis}
                      busy={busy}
                      problem={problem}
                      onReason={setReason}
                      onDecide={() => void decide(p)}
                      onCancel={cancel}
                    />
                  )}
                </dd>
                {decidable(p) && !open && (
                  <dd className={govuk ? "govuk-summary-list__actions" : undefined} style={{ margin: 0, display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
                    <button type="button" className={button(true)} onClick={(e) => start(p.id, "accept", e.currentTarget)}>
                      {p.status === "accepted" ? `Add ${title(p)} to the draft model again…` : `Add ${title(p)} to the draft model…`}
                    </button>
                    {p.status === "pending" && (
                      <button type="button" className={button(false)} onClick={(e) => start(p.id, "decline", e.currentTarget)}>
                        {`Decline ${title(p)}…`}
                      </button>
                    )}
                  </dd>
                )}
              </div>
            );
          })}
        </dl>
      )}
    </section>
  );
}

function DecisionForm(props: {
  govuk: boolean;
  proposal: ModelProposal;
  decision: Decision;
  reason: string;
  basis: Basis;
  onBasis: (value: Basis) => void;
  busy: boolean;
  problem: string | null;
  onReason: (value: string) => void;
  onDecide: () => void;
  onCancel: () => void;
}) {
  const { govuk, proposal, decision, reason, basis, onBasis, busy, problem, onReason, onDecide, onCancel } = props;
  const verb = decision === "accept" ? "Add to the draft model" : "Decline";
  const fieldId = `model-proposal-reason-${proposal.id}`;
  return (
    <div
      role="group"
      aria-label={`${verb}: ${title(proposal)}`}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          onCancel();
        } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          onDecide();
        }
      }}
      style={{ display: "grid", gap: "var(--sp-8)", paddingTop: "var(--sp-4)" }}
    >
      {problem && govuk && (
        <div className="govuk-error-summary" role="alert" tabIndex={-1}>
          <h4 className="govuk-error-summary__title" style={{ margin: 0 }}>
            There is a problem
          </h4>
          <div className="govuk-error-summary__body">
            <ul className="govuk-list govuk-error-summary__list">
              <li>
                <a href={`#${fieldId}`}>{problem}</a>
              </li>
            </ul>
          </div>
        </div>
      )}
      <div className={govuk ? `govuk-form-group${problem ? " govuk-form-group--error" : ""}` : undefined} style={{ display: "grid", gap: "var(--sp-4)" }}>
        <label htmlFor={fieldId} className={govuk ? "govuk-label" : "caption"}>
          Why? (required)
        </label>
        {problem && govuk && <p className="govuk-error-message">{problem}</p>}
        <textarea
          id={fieldId}
          className={govuk ? `govuk-textarea${problem ? " govuk-textarea--error" : ""}` : "input"}
          rows={2}
          autoFocus
          value={reason}
          disabled={busy}
          onChange={(e) => onReason(e.target.value)}
          style={{ width: "100%", boxSizing: "border-box", resize: "vertical" }}
        />
      </div>
      {decision === "accept" && (
        <fieldset className={govuk ? "govuk-fieldset" : undefined} style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: "var(--sp-4)" }}>
          <legend className={govuk ? "govuk-fieldset__legend govuk-fieldset__legend--s" : "caption"}>What stands behind its links? (required)</legend>
          <div className={govuk ? "govuk-radios govuk-radios--small" : undefined} style={govuk ? undefined : { display: "grid", gap: "var(--sp-4)" }}>
            {(["direct", "probabilistic"] as const).map((choice) => {
              const id = `model-proposal-basis-${proposal.id}-${choice}`;
              return (
                <div key={choice} className={govuk ? "govuk-radios__item" : undefined} style={govuk ? undefined : { display: "flex", gap: "var(--sp-8)", alignItems: "baseline" }}>
                  <input
                    id={id}
                    className={govuk ? "govuk-radios__input" : undefined}
                    type="radio"
                    name={`model-proposal-basis-${proposal.id}`}
                    checked={basis === choice}
                    disabled={busy}
                    onChange={() => onBasis(choice)}
                  />
                  <label htmlFor={id} className={govuk ? "govuk-label govuk-radios__label" : undefined}>
                    {choice === "direct"
                      ? "Direct: a loader backs its links, from now on (links drawn before stay probabilistic)"
                      : "Probabilistic: declared by an analyst, or statistically derived"}
                  </label>
                </div>
              );
            })}
          </div>
        </fieldset>
      )}
      {problem && !govuk && (
        <p role="alert" className="caption" style={{ margin: 0 }}>
          {problem}
        </p>
      )}
      <span style={{ display: "flex", gap: "var(--sp-8)", justifyContent: "flex-end", flexWrap: "wrap" }}>
        <button type="button" className={govuk ? "govuk-button govuk-button--secondary" : "btn"} disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button
          type="button"
          className={govuk ? `govuk-button${decision === "decline" ? " govuk-button--warning" : ""}` : "btn btn--primary"}
          disabled={busy}
          onClick={onDecide}
        >
          {verb}
        </button>
      </span>
    </div>
  );
}
