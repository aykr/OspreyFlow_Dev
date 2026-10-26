// The workspace's welcome panel (ADR-115 E6; the reference's `OspreyFlow Workspace.dc.html`): over the
// canvas's top left, what the canvas holds, the case's latest history steps to pick up from — each
// restored as the History drawer restores one (spec 03 §3.1's route) — and the keys worth knowing,
// each one the Glass has. It reopens with `?` or the rail's Help; closing it is remembered per person.
import { useEffect, useState } from "react";

import { whenLabel } from "../home/homeData";
import type { HistoryStepSummary, WorkingSetDelta } from "../workingset/models";

const KEY = (subject: string) => `ospreyflow.welcome-closed.${subject}`;

export function welcomeDismissed(subject: string): boolean {
  try {
    return localStorage.getItem(KEY(subject)) === "1";
  } catch {
    return false;
  }
}

export function setWelcomeDismissed(subject: string, closed: boolean): void {
  try {
    if (closed) localStorage.setItem(KEY(subject), "1");
    else localStorage.removeItem(KEY(subject));
  } catch {
    // Kept for this page only: the panel then opens again next time, which is the honest fallback.
  }
}

/** `?` anywhere but in a text field opens the panel (ADR-115 E6). */
export function useHelpKey(open: () => void): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.key !== "?" || event.ctrlKey || event.metaKey || event.altKey) return;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      open();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
}

const KEYS: [string, string][] = [
  ["/", "Search entities, identifiers, documents"],
  ["←→", "Move between nodes on the canvas"],
  ["Enter", "Expand the focused node by one hop"],
  ["F", "Fit the graph to the window"],
  ["Esc", "Clear the selection"],
  ["?", "Open this panel again"],
];

export interface WorkspaceWelcomeProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** How many entities the canvas holds now. */
  nodeCount: number;
  onRestored: (snapshot: WorkingSetDelta) => void;
  onClose: () => void;
  now?: Date;
}

export function WorkspaceWelcome({ apiBaseUrl, bearerToken, investigationId, nodeCount, onRestored, onClose, now = new Date() }: WorkspaceWelcomeProps) {
  const [steps, setSteps] = useState<HistoryStepSummary[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    void fetch(`${apiBaseUrl}/v1/investigations/${investigationId}/history`, { headers: { Authorization: `Bearer ${bearerToken}` } })
      .then((r) => (r.ok ? (r.json() as Promise<unknown>) : []))
      .then((body) => {
        if (cancelled) return;
        const all = Array.isArray(body) ? (body as HistoryStepSummary[]) : [];
        // Only a step that can be restored is a place to pick up from (a brief edit, ADR-128, is not).
        const restorable = all.filter((step) => step.restorable !== false);
        setSteps([...restorable].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)).slice(0, 3));
      })
      .catch(() => !cancelled && setSteps([]));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);

  async function restore(stepId: string): Promise<void> {
    const response = await fetch(`${apiBaseUrl}/v1/investigations/${investigationId}/history/${stepId}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${bearerToken}` },
    });
    if (!response.ok) return;
    onRestored((await response.json()) as WorkingSetDelta);
    onClose();
  }

  return (
    <div role="dialog" aria-modal="false" aria-labelledby="workspace-welcome-title" className="workspace-welcome">
      <div className="workspace-welcome__head">
        <h2 id="workspace-welcome-title">Welcome back</h2>
        <button type="button" className="btn btn--quiet workspace-welcome__close" aria-label="Close the welcome panel" onClick={onClose}>
          ×
        </button>
      </div>
      <p className="workspace-welcome__summary">
        {nodeCount === 0
          ? "The canvas is empty. Search, or open Explore to find where to start."
          : `The canvas shows the ${nodeCount.toLocaleString("en-GB")} ${nodeCount === 1 ? "entity" : "entities"} you were working on last.`}
      </p>
      {steps && steps.length > 0 && (
        <>
          <h3 id="workspace-welcome-history">Pick up where you left off</h3>
          <ul aria-labelledby="workspace-welcome-history" className="workspace-welcome__history">
            {steps.map((step) => (
              <li key={step.id}>
                <button type="button" className="workspace-welcome__step" onClick={() => void restore(step.id)}>
                  <span>{step.label}</span>
                  <span className="value">{whenLabel(step.created_at, now)}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      <h3 id="workspace-welcome-keys">Keys worth knowing</h3>
      <ul aria-labelledby="workspace-welcome-keys" className="workspace-welcome__keys">
        {KEYS.map(([key, what]) => (
          <li key={key}>
            <kbd className="key-cap">{key}</kbd>
            <span>{what}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
