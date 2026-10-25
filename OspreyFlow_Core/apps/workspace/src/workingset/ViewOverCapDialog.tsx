import { useLayoutEffect, useRef, useState } from "react";

import { branchByFilter } from "./branchByFilter";
import type { LimitExceeded } from "./models";

const COUNT = new Intl.NumberFormat("en-GB");

/** A window selects links, so with too many nodes it cannot help on its own (ADR-124 decision 2:
 * "types select nodes; the window selects links"). Said, and the request not sent. */
const WINDOW_ALONE =
  "A date window selects links, not nodes, so on its own it cannot bring a view with too many nodes under the limit. Choose entity types as well.";

export interface ViewOverCapDialogProps {
  /** The reader's own figure: which cap, its size, and what their view would be. */
  wouldBe: LimitExceeded;
  /** The entity types to choose from: the ontology's, never read from the case's contents (a list
   * built from what is stored could name a type only hidden material holds). */
  entityTypes: readonly string[];
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** "Try again": a resync with no last sequence. */
  onTryAgain: () => void;
  /** The new case is made: open it, as a branch is opened. */
  onBranchOpened: (id: string, name: string) => void;
  onClose: () => void;
  fetcher?: typeof fetch;
}

/** The figure, in the words the canvas's other limit refusal uses (`canvas/linksAmong.ts`). */
function figure(wouldBe: LimitExceeded): string {
  const what = wouldBe.cap_kind === "nodes" ? "nodes" : "links";
  return `Too many for the canvas: ${COUNT.format(wouldBe.would_be)} ${what} against a limit of ${COUNT.format(wouldBe.cap)}.`;
}

/**
 * What a reader is shown when the server says their own view of the open case is past a cap
 * (ADR-124 decision 2, Amendment 9): a colleague's work, or a restore that kept what its restorer
 * could not see, took it there. Two ways out, and the only figure on it is theirs: open a branch
 * of a narrower view of the case (entity types, a date window, or both), or try again, which asks
 * the server to count the view once more. Focus is held inside it; Escape closes it.
 */
export function ViewOverCapDialog({
  wouldBe,
  entityTypes,
  apiBaseUrl,
  bearerToken,
  investigationId,
  onTryAgain,
  onBranchOpened,
  onClose,
  fetcher = (input, init) => fetch(input, init),
}: ViewOverCapDialogProps) {
  const ref = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const [choosing, setChoosing] = useState(false);
  const [types, setTypes] = useState<ReadonlySet<string>>(new Set());
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useLayoutEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    // Focus that leaves the dialog while it is open (a click on the canvas behind it, a script)
    // comes straight back: it is modal.
    const onFocusIn = (e: FocusEvent) => {
      if (ref.current && e.target instanceof Node && !ref.current.contains(e.target)) {
        ref.current.querySelector<HTMLElement>("button")?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("focusin", onFocusIn);
    ref.current?.querySelector<HTMLElement>("button")?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("focusin", onFocusIn);
    };
  }, []);

  function holdFocus(event: React.KeyboardEvent<HTMLDivElement>): void {
    if (event.key !== "Tab") return;
    const controls = Array.from(
      ref.current?.querySelectorAll<HTMLElement>("button, input, select, textarea, [href]") ?? [],
    ).filter((control) => !control.hasAttribute("disabled"));
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

  function toggle(type: string): void {
    setTypes((current) => {
      const next = new Set(current);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (types.size === 0 && !from && !to) {
      setMessage("Choose entity types, a date window, or both.");
      return;
    }
    if (types.size === 0 && wouldBe.cap_kind === "nodes") {
      setMessage(WINDOW_ALONE);
      return;
    }
    setBusy(true);
    setMessage(null);
    const result = await branchByFilter(fetcher, {
      apiBaseUrl,
      bearerToken,
      investigationId,
      entityTypes: types.size > 0 ? entityTypes.filter((type) => types.has(type)) : undefined,
      validFrom: from || undefined,
      validTo: to || undefined,
    });
    setBusy(false);
    if (result.ok) {
      onBranchOpened(result.id, result.name);
    } else if (result.kind === "limit_exceeded") {
      setMessage(`${figure(result.wouldBe)} Narrow the choice and try again.`);
    } else if (result.kind === "nothing_matched") {
      setMessage("Nothing matched that choice. Choose other types or dates.");
    } else if (result.kind === "nothing_chosen") {
      setMessage("Choose entity types, a date window, or both.");
    } else {
      setMessage(result.message);
    }
  }

  return (
    <div
      className="view-over-cap"
      role="dialog"
      aria-modal="true"
      aria-labelledby="view-over-cap-title"
      ref={ref}
      onKeyDown={holdFocus}
    >
      <h2 id="view-over-cap-title" className="view-over-cap__title">
        Your view of this case is too large
      </h2>
      <p className="view-over-cap__figure">{figure(wouldBe)}</p>
      <p className="view-over-cap__why">
        Work in this case by others has taken the part of it you are cleared to see past what the
        canvas can hold. You can open a smaller view of it as a branch, or try again.
      </p>
      <div className="view-over-cap__actions">
        <button
          type="button"
          className="btn btn--primary"
          aria-expanded={choosing}
          onClick={() => setChoosing(true)}
        >
          Open a filtered branch
        </button>
        <button type="button" className="btn" onClick={onTryAgain}>
          Try again
        </button>
      </div>
      {choosing && (
        <form className="view-over-cap__form" onSubmit={(e) => void submit(e)}>
          <fieldset className="view-over-cap__types">
            <legend>Entity types</legend>
            {entityTypes.map((type) => (
              <label key={type} className="view-over-cap__type">
                <input type="checkbox" checked={types.has(type)} onChange={() => toggle(type)} />
                {type}
              </label>
            ))}
          </fieldset>
          {wouldBe.cap_kind === "nodes" && <p className="view-over-cap__hint">{WINDOW_ALONE}</p>}
          <div className="view-over-cap__window">
            <label>
              From
              <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
            </label>
            <label>
              To
              <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
            </label>
          </div>
          <button type="submit" className="btn btn--primary" disabled={busy}>
            Open branch
          </button>
        </form>
      )}
      {message !== null && (
        <p className="view-over-cap__message" role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
