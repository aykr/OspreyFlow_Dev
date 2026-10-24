export interface ToastProps {
  message: string;
  kind?: "info" | "error" | "warning" | "success";
}

/** A short message that says what happened, so it is never a silent state change. The retired
 * `notice` step (ADR-124) no longer reaches it. */
const SAID: Record<Exclude<ToastProps["kind"], "info" | undefined>, { glyph: string; word: string }> = {
  error: { glyph: "!", word: "Error" },
  warning: { glyph: "△", word: "Warning" },
  success: { glyph: "✓", word: "Done" },
};

/** A kind other than information is said by a glyph and in words, never by colour alone (DESIGN.md
 * §3.3). */
export function Toast({ message, kind = "info" }: ToastProps) {
  const said = kind === "info" ? null : SAID[kind];
  const className = ["toast", said ? `toast--${kind}` : ""].filter(Boolean).join(" ");
  return (
    <div className={className} role="status">
      {said && (
        <span className="toast__glyph" aria-hidden="true">
          {said.glyph}
        </span>
      )}
      <span>
        {said && `${said.word}: `}
        {message}
      </span>
    </div>
  );
}
