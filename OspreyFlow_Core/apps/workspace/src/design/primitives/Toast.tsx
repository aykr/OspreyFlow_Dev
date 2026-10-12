export interface ToastProps {
  message: string;
  kind?: "info" | "error" | "warning" | "success";
}

/** `spec/02_GLASS_FRONTEND.md` §3.2's `notice` op reaches the analyst
 * through here — "N item(s) withheld by handling policy" is a toast, not
 * a silent state change (the status-bar
 * requirement: the analyst must never mistake a filtered picture for a
 * complete one). */
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
