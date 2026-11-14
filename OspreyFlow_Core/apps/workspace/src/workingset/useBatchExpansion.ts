import { useCallback, useState } from "react";

import type { BatchExpansionRequest } from "./batchExpansionApi";

/** One choice of *Run as a batch job* (ADR-151): the expansion handed up, with the case and the person it was
 * asked in and for. `n` counts the choices, so each has its own panel (its own `key`). */
export interface BatchExpansionAsked {
  request: BatchExpansionRequest;
  caseId: string;
  who: string | null;
  n: number;
}

/**
 * The App's hold on the batch job's panel. A choice belongs to the case and the person signed in when it was
 * made: another case opened, or someone else signed in in place, drops it in the same render, so the panel never
 * follows one case's job in another, nor shows one person's refused figure to the next (rule 7). The job itself
 * keeps running on the server. A choice made again while one is held opens a new panel, which the Conduit's 409
 * makes follow the job already running.
 */
export function useBatchExpansion(caseId: string | null, who: string | null) {
  const [asked, setAsked] = useState<BatchExpansionAsked | null>(null);
  const current = asked !== null && asked.caseId === caseId && asked.who === who ? asked : null;
  if (asked !== null && current === null) setAsked(null);
  const ask = useCallback(
    (request: BatchExpansionRequest) => {
      if (!caseId) return;
      setAsked((held) => ({ request, caseId, who, n: (held?.n ?? 0) + 1 }));
    },
    [caseId, who],
  );
  const close = useCallback(() => setAsked(null), []);
  return { asked: current, ask, close };
}
