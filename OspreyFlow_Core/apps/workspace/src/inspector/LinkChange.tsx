import { useEffect, useRef, useState } from "react";

import type { Edge, EdgeTypeDef } from "../../../../packages/schemas/generated";
import { linkTypeName } from "../canvas/linkLabel";
import { LinkChangeError, changeLink, type LinkChangeResult } from "./linkChangeApi";
import {
  MAX_REASON_CHARS,
  basisChoicesFor,
  initialDraft,
  retypeDraft,
  toChangeInput,
  typesFor,
  type LinkDraft,
} from "./linkChangeForm";

export interface LinkChangeProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  edge: Edge;
  /** The entity types at the two ends, which decide the link types it may change to. */
  sourceType: string;
  targetType: string;
  edgeTypes: readonly EdgeTypeDef[];
  /** Counts up each time the link menu's *Change link…* is chosen, which opens the form. */
  openSignal?: number;
  /** Told of the result so the caller can put the new link in the view. */
  onChanged: (result: LinkChangeResult) => void;
}

function sentence(error: unknown): string {
  if (error instanceof LinkChangeError) {
    if (error.kind === "invalid" || error.kind === "nothing_changed" || error.kind === "resolution_link") {
      return error.message;
    }
    if (error.kind === "link_not_found") return "This link is no longer in your view, so it was not changed.";
    if (error.kind === "forbidden") {
      return "The link was not changed. You can read this case but not change it.";
    }
  }
  return "The link was not changed. Nothing was recorded; try again.";
}

/** The Inspector's **Change this link** form (ADR-080, `02_GLASS_FRONTEND.md` §3.1f): the link's
 * type and its details (what the type records, its dates, the records behind it), and a reason,
 * which is required. Saving replaces the link and keeps the old one and what was changed in its
 * history. Same-as links are not offered it: they are confirmed or marked as not the same. */
export function LinkChange({
  apiBaseUrl,
  bearerToken,
  investigationId,
  edge,
  sourceType,
  targetType,
  edgeTypes,
  openSignal = 0,
  onChanged,
}: LinkChangeProps) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<LinkDraft>(() => initialDraft(edge));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const typeRef = useRef<HTMLSelectElement>(null);

  // A different link (or the new one after a change) starts from itself, closed.
  useEffect(() => {
    setDraft(initialDraft(edge));
    setProblem(null);
    setOpen(false);
  }, [edge]);

  useEffect(() => {
    if (openSignal > 0) {
      setOpen(true);
      setSaved(false);
    }
  }, [openSignal]);

  useEffect(() => {
    if (open) typeRef.current?.focus();
  }, [open]);

  const choices = typesFor(edgeTypes, sourceType, targetType);
  const typeDef = edgeTypes.find((t) => t.name === draft.type);
  const showDates = typeDef?.temporal === true || edge.interval != null;
  // ADR-081 step B: what stands behind the link is asked each time, with no default. With one
  // possible answer (a Probabilistic type, or a link already marked) it is stated, not asked.
  const bases = basisChoicesFor(edge, typeDef);

  const save = async () => {
    if (busy) return;
    const outcome = toChangeInput(edge, draft, edgeTypes);
    if (outcome.kind === "nothing") {
      setProblem("Nothing about the link has been changed yet.");
      return;
    }
    if (outcome.kind === "problem") {
      setProblem(outcome.message);
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      const result = await changeLink(apiBaseUrl, bearerToken, investigationId, edge.id, outcome.input);
      setSaved(true);
      setOpen(false);
      onChanged(result);
    } catch (error) {
      setProblem(sentence(error));
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <section aria-label="Change this link" style={{ marginTop: "var(--sp-16)" }}>
        <button type="button" className="btn" onClick={() => { setOpen(true); setSaved(false); }}>
          Change this link…
        </button>
        {saved && (
          <p role="status" style={{ color: "var(--text-secondary)" }}>
            Link changed. The old link and what changed are kept in its history.
          </p>
        )}
      </section>
    );
  }

  return (
    <section
      aria-label="Change this link"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          setOpen(false);
          setDraft(initialDraft(edge));
          setProblem(null);
        } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          void save();
        }
      }}
      style={{ marginTop: "var(--sp-16)", display: "grid", gap: "var(--sp-8)" }}
    >
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)", color: "var(--text-secondary)" }}>
        Change this link
      </h3>

      <label style={{ display: "grid", gap: "var(--sp-4)" }}>
        <span style={{ fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>Link type</span>
        <select
          ref={typeRef}
          className="input"
          value={draft.type}
          disabled={busy}
          onChange={(e) => setDraft(retypeDraft(draft, e.target.value, edgeTypes))}
        >
          {choices.map((t) => (
            <option key={t.name} value={t.name}>
              {linkTypeName(t.name, edgeTypes)}
            </option>
          ))}
        </select>
      </label>

      {(typeDef?.properties ?? []).map((def) => (
        <label key={def.name} style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span style={{ fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>
            {def.name}
            {def.required ? " (required)" : ""}
            {def.type === "string[]" ? " (separate with commas)" : ""}
          </span>
          {def.type === "enum" ? (
            <select
              className="input"
              value={draft.properties[def.name] ?? ""}
              disabled={busy}
              onChange={(e) =>
                setDraft({ ...draft, properties: { ...draft.properties, [def.name]: e.target.value } })
              }
            >
              <option value="">(none)</option>
              {(def.values ?? []).map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          ) : def.type === "boolean" ? (
            <select
              className="input"
              value={draft.properties[def.name] ?? ""}
              disabled={busy}
              onChange={(e) =>
                setDraft({ ...draft, properties: { ...draft.properties, [def.name]: e.target.value } })
              }
            >
              <option value="">(none)</option>
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          ) : (
            <input
              className="input"
              type="text"
              value={draft.properties[def.name] ?? ""}
              disabled={busy}
              onChange={(e) =>
                setDraft({ ...draft, properties: { ...draft.properties, [def.name]: e.target.value } })
              }
            />
          )}
        </label>
      ))}

      {bases.length > 1 && (
        <div style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span id="link-basis-label" style={{ fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>
            What stands behind it? (required)
          </span>
          <div role="radiogroup" aria-labelledby="link-basis-label" style={{ display: "grid", gap: "var(--sp-4)" }}>
            <label style={{ display: "flex", gap: "var(--sp-8)", alignItems: "baseline" }}>
              <input
                type="radio"
                name="link-basis"
                value="direct"
                checked={draft.basis === "direct"}
                disabled={busy}
                onChange={() => setDraft({ ...draft, basis: "direct" })}
              />
              <span>
                Direct
                <span style={{ color: "var(--text-tertiary)" }}> — a loaded record stands behind it</span>
              </span>
            </label>
            <label style={{ display: "flex", gap: "var(--sp-8)", alignItems: "baseline" }}>
              <input
                type="radio"
                name="link-basis"
                value="probabilistic"
                checked={draft.basis === "probabilistic"}
                disabled={busy}
                onChange={() => setDraft({ ...draft, basis: "probabilistic" })}
              />
              <span>
                Probabilistic
                <span style={{ color: "var(--text-tertiary)" }}> — statistically derived, or declared by you</span>
              </span>
            </label>
          </div>
        </div>
      )}
      {bases.length === 1 && (
        <p style={{ margin: 0, fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>
          What stands behind it: <span style={{ color: "var(--text-primary)" }}>Probabilistic</span> — the only
          basis this link may have. A link is never promoted to Direct by hand.
        </p>
      )}

      <label style={{ display: "grid", gap: "var(--sp-4)" }}>
        <span style={{ fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>Records behind it</span>
        <input
          className="input"
          type="number"
          min={1}
          step={1}
          value={draft.occurrences}
          disabled={busy}
          onChange={(e) => setDraft({ ...draft, occurrences: e.target.value })}
        />
      </label>

      {showDates && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-8)" }}>
          <label style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span style={{ fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>From</span>
            <input
              className="input"
              type="date"
              value={draft.validFrom}
              disabled={busy}
              onChange={(e) => setDraft({ ...draft, validFrom: e.target.value })}
            />
          </label>
          <label style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span style={{ fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>To</span>
            <input
              className="input"
              type="date"
              value={draft.validTo}
              disabled={busy}
              onChange={(e) => setDraft({ ...draft, validTo: e.target.value })}
            />
          </label>
        </div>
      )}

      <label style={{ display: "grid", gap: "var(--sp-4)" }}>
        <span style={{ fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>
          Why is it being changed? (required)
        </span>
        <textarea
          className="input"
          rows={3}
          maxLength={MAX_REASON_CHARS}
          value={draft.reason}
          disabled={busy}
          onChange={(e) => setDraft({ ...draft, reason: e.target.value })}
          style={{ width: "100%", boxSizing: "border-box", resize: "vertical" }}
        />
      </label>

      <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
        The old link is kept. This change, who made it and why are recorded in the link&rsquo;s
        history and in the audit trail.
      </p>

      {problem && (
        <p role="alert" style={{ color: "var(--text-secondary)", margin: 0 }}>
          {problem}
        </p>
      )}

      <div style={{ display: "flex", gap: "var(--sp-8)", justifyContent: "flex-end" }}>
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            setOpen(false);
            setDraft(initialDraft(edge));
            setProblem(null);
          }}
        >
          Cancel
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={busy || draft.reason.trim() === ""}
          onClick={() => void save()}
        >
          Save change
        </button>
      </div>
    </section>
  );
}
