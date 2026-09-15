export interface ToastProps {
  message: string;
  kind?: "info" | "error" | "warning" | "success";
}

/** `docs/02_GLASS_FRONTEND.md` §3.2's `notice` op reaches the analyst
 * through here — "N item(s) withheld by handling policy" is a toast, not
 * a silent state change (`docs/07_BUILD_PLAN.md` Phase 4's status-bar
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
