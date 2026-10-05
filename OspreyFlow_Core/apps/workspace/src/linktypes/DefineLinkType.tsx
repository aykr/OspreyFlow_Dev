// *Define a new type…* (ADR-090 C2, spec 02 §3.1f): when no type fits a link, an Editor proposes one
// here, from the change form. It is usable at once in this case, its branches and wherever one of
// its links is seen, and it is probabilistic until an administrator of the unit decides. What the
// analyst types is checked here first (`defineType.ts`) and again by the server, whose sentence is
// shown when it refuses.
import { useEffect, useRef, useState } from "react";

import type { EdgeTypeDef } from "../../../../packages/schemas/generated";
import {
  MAX_PROPOSAL_REASON_CHARS,
  TYPE_COLOURS,
  emptyTypeDraft,
  toProposal,
  typeIdFrom,
  type TypeDraft,
} from "./defineType";
import { LinkTypeError, proposeLinkType, type LinkTypeProposal } from "./linkTypesApi";

export interface DefineLinkTypeProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  sourceType: string;
  targetType: string;
  /** The types already offered here, whose names are refused. */
  offered: readonly EdgeTypeDef[];
  onProposed: (proposal: LinkTypeProposal) => void;
  onCancel: () => void;
}

/** The type a proposal declares, as the change form and the canvas read it until the case's list
 * is read again: probabilistic and analyst-defined, as the server composes it. */
export function definitionOf(proposal: LinkTypeProposal): EdgeTypeDef {
  return {
    name: proposal.name,
    from: proposal.from_types,
    to: proposal.to_types,
    directed: proposal.directed,
    basis: "probabilistic",
    colour: proposal.colour ?? null,
    thickness: proposal.thickness ?? null,
    label: proposal.label ?? null,
    analyst_defined: true,
  };
}

function sentence(error: unknown): string {
  if (error instanceof LinkTypeError) {
    if (error.kind === "refused") return error.message;
    if (error.kind === "forbidden") return "The type was not proposed. You can read this case but not change it.";
  }
  return "The type was not proposed. Nothing was recorded; try again.";
}

const small = { fontSize: "var(--fs-12)", color: "var(--text-secondary)" } as const;

export function DefineLinkType(props: DefineLinkTypeProps) {
  const { sourceType, targetType, offered, onProposed, onCancel } = props;
  const [draft, setDraft] = useState<TypeDraft>(() => emptyTypeDraft(sourceType, targetType));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const labelRef = useRef<HTMLInputElement>(null);

  useEffect(() => labelRef.current?.focus(), []);

  const propose = async () => {
    if (busy) return;
    const outcome = toProposal(draft, offered);
    if (outcome.kind === "problem") {
      setProblem(outcome.message);
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      onProposed(await proposeLinkType(props.apiBaseUrl, props.bearerToken, props.investigationId, outcome.input));
    } catch (error) {
      setProblem(sentence(error));
    } finally {
      setBusy(false);
    }
  };

  const ends = sourceType === targetType ? `${sourceType} and ${sourceType}` : `${sourceType} to ${targetType}`;
  return (
    <section
      aria-label="Define a new type"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          onCancel();
        } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          e.stopPropagation();
          void propose();
        }
      }}
      style={{
        display: "grid",
        gap: "var(--sp-8)",
        padding: "var(--sp-8)",
        border: "1px solid var(--border)",
        borderRadius: "var(--sp-4)",
      }}
    >
      <h4 style={{ margin: 0, fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>Define a new type</h4>
      <label style={{ display: "grid", gap: "var(--sp-4)" }}>
        <span style={small}>Name (required)</span>
        <input
          ref={labelRef}
          className="input"
          type="text"
          value={draft.label}
          disabled={busy}
          placeholder="Known to"
          onChange={(e) =>
            setDraft({ ...draft, label: e.target.value, id: draft.idTyped ? draft.id : typeIdFrom(e.target.value) })
          }
        />
      </label>
      <label style={{ display: "grid", gap: "var(--sp-4)" }}>
        <span style={small}>Type ID</span>
        <input
          className="input"
          type="text"
          value={draft.id}
          disabled={busy}
          onChange={(e) => setDraft({ ...draft, id: e.target.value.toUpperCase(), idTyped: true })}
        />
      </label>
      <p style={{ ...small, margin: 0 }}>Between {ends}.</p>
      <label style={{ display: "flex", gap: "var(--sp-8)", alignItems: "baseline" }}>
        <input
          type="checkbox"
          checked={draft.eitherWay}
          disabled={busy}
          onChange={(e) => setDraft({ ...draft, eitherWay: e.target.checked })}
        />
        <span>Either way round</span>
      </label>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-8)" }}>
        <label style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span style={small}>Colour</span>
          <select
            className="input"
            value={draft.colour}
            disabled={busy}
            onChange={(e) => setDraft({ ...draft, colour: e.target.value })}
          >
            <option value="">(the usual)</option>
            {TYPE_COLOURS.map((c) => (
              <option key={c} value={c}>
                {c[0]!.toUpperCase() + c.slice(1)}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span style={small}>Thickness</span>
          <select
            className="input"
            value={draft.thickness}
            disabled={busy}
            onChange={(e) => setDraft({ ...draft, thickness: e.target.value })}
          >
            <option value="">(by weight)</option>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={String(n)}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label style={{ display: "grid", gap: "var(--sp-4)" }}>
        <span style={small}>Why does no type fit? (required)</span>
        <textarea
          className="input"
          rows={2}
          maxLength={MAX_PROPOSAL_REASON_CHARS}
          value={draft.reason}
          disabled={busy}
          onChange={(e) => setDraft({ ...draft, reason: e.target.value })}
          style={{ width: "100%", boxSizing: "border-box", resize: "vertical" }}
        />
      </label>
      <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
        Usable at once in this case, and drawn dotted: a proposed type is probabilistic until an
        administrator of your unit promotes it.
      </p>
      {problem && (
        <p role="alert" style={{ color: "var(--text-secondary)", margin: 0 }}>
          {problem}
        </p>
      )}
      <div style={{ display: "flex", gap: "var(--sp-8)", justifyContent: "flex-end" }}>
        <button type="button" className="btn" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="btn btn--primary" disabled={busy} onClick={() => void propose()}>
          Propose type
        </button>
      </div>
    </section>
  );
}
