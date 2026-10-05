// The administrator's *Proposed types* list (ADR-090 C3, spec 02 §3.1f): the relationship types
// analysts of the administrator's own unit proposed, each to promote (choosing Direct or
// Probabilistic, and a new ID when its name is taken by a type its links do not fit), reject, or,
// once promoted, retire. Every decision needs a reason. The server holds the rules and its sentence
// is shown when it refuses; nothing here decides on the administrator's behalf.
import { useCallback, useEffect, useState } from "react";

import { Drawer } from "../design/primitives/Drawer";
import { typeIdFrom } from "./defineType";
import {
  LinkTypeError,
  listProposals,
  promoteProposal,
  rejectProposal,
  retireLinkType,
  type LinkTypeProposal,
} from "./linkTypesApi";

export interface ProposedTypesProps {
  apiBaseUrl: string;
  bearerToken: string;
  open: boolean;
  onClose: () => void;
  /** Told after each decision, so the case's types are read again. */
  onDecided?: () => void;
}

type Action = "promote" | "reject" | "retire";

interface Deciding {
  proposal: LinkTypeProposal;
  action: Action;
  basis: "" | "direct" | "probabilistic";
  renameTo: string;
  /** Shown once the server has said the name is taken. */
  askRename: boolean;
  reason: string;
}

const STATUS_WORDS: Record<LinkTypeProposal["status"], string> = {
  pending: "Proposed",
  promoted: "Promoted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  merged: "Merged",
  retired: "Retired",
};

function title(p: LinkTypeProposal): string {
  return p.label?.trim() || p.name;
}

function ends(p: LinkTypeProposal): string {
  const from = p.from_types.join(" or ");
  const to = p.to_types.join(" or ");
  return p.directed ? `${from} to ${to}` : `${from} and ${to}, either way`;
}

function sentence(error: unknown): string {
  if (error instanceof LinkTypeError) {
    if (error.kind === "refused") return error.message;
    if (error.kind === "not_found") return "That proposal is no longer there to decide.";
    if (error.kind === "forbidden") return "Deciding proposals needs the administrator role.";
  }
  return "Nothing was decided; try again.";
}

const small = { fontSize: "var(--fs-12)", color: "var(--text-secondary)" } as const;

export function ProposedTypes({ apiBaseUrl, bearerToken, open, onClose, onDecided }: ProposedTypesProps) {
  const [proposals, setProposals] = useState<LinkTypeProposal[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [deciding, setDeciding] = useState<Deciding | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setProposals(await listProposals(apiBaseUrl, bearerToken));
      setLoadFailed(false);
    } catch {
      setLoadFailed(true);
    }
  }, [apiBaseUrl, bearerToken]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const start = (proposal: LinkTypeProposal, action: Action) => {
    setDeciding({ proposal, action, basis: "", renameTo: "", askRename: false, reason: "" });
    setProblem(null);
    setDone(null);
  };

  const decide = async () => {
    if (!deciding || busy) return;
    const { proposal, action } = deciding;
    const reason = deciding.reason.trim();
    if (action === "promote" && deciding.basis === "") {
      setProblem("Say what stands behind its links: Direct or Probabilistic.");
      return;
    }
    if (reason === "") {
      setProblem("Say why: a reason is required.");
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      let words: string;
      if (action === "promote") {
        const renameTo = deciding.askRename ? typeIdFrom(deciding.renameTo) : "";
        const result = await promoteProposal(apiBaseUrl, bearerToken, proposal.id, {
          basis: deciding.basis as "direct" | "probabilistic",
          reason,
          ...(renameTo ? { rename_to: renameTo } : {}),
        });
        words =
          result.status === "merged"
            ? `${title(proposal)} merged into ${result.promoted_name ?? proposal.name}.`
            : `${title(proposal)} promoted: offered in every case now.`;
      } else if (action === "reject") {
        await rejectProposal(apiBaseUrl, bearerToken, proposal.id, reason);
        words = `${title(proposal)} rejected: no longer offered. Its links stay.`;
      } else {
        await retireLinkType(apiBaseUrl, bearerToken, proposal.promoted_name ?? proposal.name, reason);
        words = `${title(proposal)} retired: no longer offered. Its links stay.`;
      }
      setDeciding(null);
      setDone(words);
      onDecided?.();
      await load();
    } catch (error) {
      const message = sentence(error);
      setProblem(message);
      // A name taken by a type its links do not fit: promote it under a new ID.
      if (action === "promote" && /new name/i.test(message)) setDeciding({ ...deciding, askRename: true });
    } finally {
      setBusy(false);
    }
  };

  const verb = deciding ? { promote: "Promote", reject: "Reject", retire: "Retire" }[deciding.action] : "";

  return (
    <Drawer open={open} onClose={onClose} title="Proposed types">
      <div style={{ display: "grid", gap: "var(--sp-12)" }}>
        {loadFailed && (
          <p role="alert" style={{ margin: 0, color: "var(--text-secondary)" }}>
            The proposed types could not be read. Close this and try again.
          </p>
        )}
        {done && (
          <p role="status" style={{ margin: 0, color: "var(--text-secondary)" }}>
            {done}
          </p>
        )}
        {proposals !== null && proposals.length === 0 && !loadFailed && (
          <p style={{ margin: 0, color: "var(--text-secondary)" }}>No proposals from your unit.</p>
        )}
        {(proposals ?? []).map((p) => (
          <article key={p.id} style={{ display: "grid", gap: "var(--sp-4)", borderBottom: "1px solid var(--border)", paddingBottom: "var(--sp-8)" }}>
            <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "baseline" }}>
              <strong>{title(p)}</strong>
              <span style={small}>{STATUS_WORDS[p.status]}</span>
            </div>
            <span style={small}>
              {p.name} · {ends(p)}
            </span>
            <span style={small}>
              Proposed by {p.proposed_by} in case {p.investigation_id}: “{p.reason}”
            </span>
            {p.status === "pending" && (
              <span style={{ display: "flex", gap: "var(--sp-8)" }}>
                <button type="button" className="btn" aria-label={`Promote ${title(p)}…`} onClick={() => start(p, "promote")}>
                  Promote…
                </button>
                <button type="button" className="btn" aria-label={`Reject ${title(p)}…`} onClick={() => start(p, "reject")}>
                  Reject…
                </button>
              </span>
            )}
            {p.status === "promoted" && (
              <span>
                <button type="button" className="btn" aria-label={`Retire ${title(p)}…`} onClick={() => start(p, "retire")}>
                  Retire…
                </button>
              </span>
            )}
            {deciding?.proposal.id === p.id && (
              <DecisionForm
                deciding={deciding}
                verb={verb}
                busy={busy}
                problem={problem}
                onChange={setDeciding}
                onDecide={() => void decide()}
                onCancel={() => {
                  setDeciding(null);
                  setProblem(null);
                }}
              />
            )}
          </article>
        ))}
      </div>
    </Drawer>
  );
}

function DecisionForm(props: {
  deciding: Deciding;
  verb: string;
  busy: boolean;
  problem: string | null;
  onChange: (next: Deciding) => void;
  onDecide: () => void;
  onCancel: () => void;
}) {
  const { deciding, verb, busy, problem, onChange, onDecide, onCancel } = props;
  return (
    <section
      aria-label={`${verb} ${title(deciding.proposal)}`}
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
      {deciding.action === "promote" && (
        <div role="radiogroup" aria-label="What stands behind its links? (required)" style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span style={small}>What stands behind its links? (required)</span>
          {(["direct", "probabilistic"] as const).map((basis) => (
            <label key={basis} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "baseline" }}>
              <input
                type="radio"
                name={`basis-${deciding.proposal.id}`}
                checked={deciding.basis === basis}
                disabled={busy}
                onChange={() => onChange({ ...deciding, basis })}
              />
              <span>
                {basis === "direct" ? "Direct" : "Probabilistic"}
                <span style={{ color: "var(--text-tertiary)" }}>
                  {basis === "direct"
                    ? " — a loader backs it; links already drawn stay probabilistic"
                    : " — statistically derived, or declared by an analyst"}
                </span>
              </span>
            </label>
          ))}
        </div>
      )}
      {deciding.action === "promote" && deciding.askRename && (
        <label style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span style={small}>Promote as (a new type ID)</span>
          <input
            className="input"
            type="text"
            autoFocus
            value={deciding.renameTo}
            disabled={busy}
            onChange={(e) => onChange({ ...deciding, renameTo: e.target.value.toUpperCase() })}
          />
        </label>
      )}
      <label style={{ display: "grid", gap: "var(--sp-4)" }}>
        <span style={small}>Why? (required)</span>
        <textarea
          className="input"
          rows={2}
          autoFocus={!deciding.askRename}
          value={deciding.reason}
          disabled={busy}
          onChange={(e) => onChange({ ...deciding, reason: e.target.value })}
          style={{ width: "100%", boxSizing: "border-box", resize: "vertical" }}
        />
      </label>
      {problem && (
        <p role="alert" style={{ margin: 0, color: "var(--text-secondary)" }}>
          {problem}
        </p>
      )}
      <span style={{ display: "flex", gap: "var(--sp-8)", justifyContent: "flex-end" }}>
        <button type="button" className="btn" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="btn btn--primary" disabled={busy} onClick={onDecide}>
          {verb}
        </button>
      </span>
    </section>
  );
}
