import { useState } from "react";

import { Popover } from "../design/primitives/Popover";

/** The same limit the server holds for a reason (`services/api/link_changes.py::MAX_REASON_CHARS`). */
export const MAX_REASON = 1000;

export interface ReasonPromptProps {
  x: number;
  y: number;
  /** What is being asked, in a line: "Confirm these two as the same". */
  title: string;
  confirmLabel: string;
  /** Called with the reason, trimmed and never empty. */
  onSubmit: (reason: string) => void;
  onCancel: () => void;
}

/** A small box that asks *why* before a write from the link menu (ADR-080: every write says why
 * and is recorded with who made it). The reason is required: the button stays off until there is
 * one. Control-Enter confirms and Escape cancels, so it can be used without a mouse. */
export function ReasonPrompt({ x, y, title, confirmLabel, onSubmit, onCancel }: ReasonPromptProps) {
  const [reason, setReason] = useState("");
  const ready = reason.trim() !== "";
  const submit = () => {
    if (ready) onSubmit(reason.trim());
  };
  return (
    <Popover x={x} y={y} onClose={onCancel}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)", minWidth: 280 }}>
        <strong className="value">{title}</strong>
        <label style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span style={{ fontSize: "var(--fs-12)", color: "var(--text-secondary)" }}>
            Why? (required, kept in the audit trail)
          </span>
          <textarea
            className="input"
            rows={3}
            tabIndex={0}
            maxLength={MAX_REASON}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                submit();
              }
            }}
            style={{ width: "100%", boxSizing: "border-box", resize: "vertical" }}
          />
        </label>
        <div style={{ display: "flex", gap: "var(--sp-8)", justifyContent: "flex-end" }}>
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn btn--primary" disabled={!ready} onClick={submit}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </Popover>
  );
}
