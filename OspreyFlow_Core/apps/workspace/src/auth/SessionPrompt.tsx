import { useLayoutEffect, useRef } from "react";

/**
 * Asked over the page, in place, when the token could not be renewed (`06_DECISIONS.md` ADR-050
 * Amendment 1, build order step 18b): the page behind it stays as it is — the open tab, the
 * selection, the map, anything typed — and signing in again happens in a small window of its own,
 * not by reloading this one. ADR-044's distinction is kept: an identity provider that could not be
 * reached is not said as an ended session, and can be tried again.
 *
 * Modal: focus starts on its first button and stays inside it. Escape does not put it away, since
 * nothing behind it can reach the Conduit until the person has signed in again.
 */
export interface SessionPromptProps {
  why: "ended" | "unreachable";
  onSignInAgain: () => void;
  onTryAgain: () => void;
  busy?: boolean;
  problem?: string | null;
}

const TITLE = {
  ended: "Your session has ended",
  unreachable: "The sign-in service could not be reached",
} as const;

const BODY = {
  ended: "Sign in again to carry on. This page stays as it is while you do: nothing on it is lost.",
  unreachable:
    "Your sign-in could not be renewed, because the sign-in service did not answer. Your work is still here. Try again, or sign in again.",
} as const;

export function SessionPrompt({ why, onSignInAgain, onTryAgain, busy = false, problem = null }: SessionPromptProps) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const onFocusIn = (e: FocusEvent) => {
      if (ref.current && e.target instanceof Node && !ref.current.contains(e.target)) {
        ref.current.querySelector<HTMLElement>("button")?.focus();
      }
    };
    document.addEventListener("focusin", onFocusIn);
    ref.current?.querySelector<HTMLElement>("button")?.focus();
    return () => document.removeEventListener("focusin", onFocusIn);
  }, [why]);

  function holdFocus(event: React.KeyboardEvent<HTMLDivElement>): void {
    if (event.key !== "Tab") return;
    const controls = Array.from(ref.current?.querySelectorAll<HTMLElement>("button") ?? []).filter(
      (control) => !control.hasAttribute("disabled"),
    );
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (first === undefined || last === undefined) return;
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !ref.current?.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !ref.current?.contains(active))) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      className="session-prompt"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="session-prompt-title"
      aria-describedby="session-prompt-body"
      ref={ref}
      onKeyDown={holdFocus}
    >
      <h2 id="session-prompt-title" className="session-prompt__title">
        {TITLE[why]}
      </h2>
      <p id="session-prompt-body" className="session-prompt__body">
        {BODY[why]}
      </p>
      <div className="session-prompt__actions">
        {why === "unreachable" && (
          <button type="button" className="btn btn--primary" onClick={onTryAgain} disabled={busy}>
            Try again
          </button>
        )}
        <button
          type="button"
          className={why === "ended" ? "btn btn--primary" : "btn"}
          onClick={onSignInAgain}
          disabled={busy}
        >
          Sign in again
        </button>
      </div>
      {problem && (
        <p className="session-prompt__problem" role="status">
          {problem}
        </p>
      )}
    </div>
  );
}
