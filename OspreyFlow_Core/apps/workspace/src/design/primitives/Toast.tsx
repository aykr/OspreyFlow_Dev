export interface ToastProps {
  message: string;
  kind?: "info" | "error" | "warning" | "success";
}

/** `spec/02_GLASS_FRONTEND.md` §3.2's `notice` op reaches the analyst
 * through here — "N item(s) withheld by handling policy" is a toast, not
 * a silent state change (the status-bar
 * requirement: the analyst must never mistake a filtered picture for a
 * complete one). */
export function Toast({ message, kind = "info" }: ToastProps) {
  const className = ["toast", kind !== "info" ? `toast--${kind}` : ""].filter(Boolean).join(" ");
  return (
    <div className={className} role="status">
      {message}
    </div>
  );
}
