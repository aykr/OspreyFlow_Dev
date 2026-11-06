// What the Studio's four places read in common (ADR-140 decision 1): the case's pipelines (the
// recipe registry, already limited to the case's datasets, ADR-099 Amendment 3) and, for each
// deployed one, its runs from the ledger (ADR-110 decision 6). Read once for the readiness strip and
// the Runs tab, and read again when either says something changed.
import { useCallback, useEffect, useState } from "react";

import type { ScheduleRunView, StudioRecipeDraft } from "../../../../../packages/schemas/generated";
import { fetchRecipeRegistry, fetchRecipeRuns } from "../api";

export interface StudioData {
  /** Every pipeline but a previous version; `null` until read. */
  pipelines: StudioRecipeDraft[] | null;
  /** Each deployed pipeline's runs, newest first, by recipe id. A pipeline whose runs the person may
   * not read is absent, not shown as never run. */
  runs: Record<string, ScheduleRunView[]>;
  problem: string | null;
  reload: () => void;
}

/** A deployed pipeline: one a run or schedule acts on (published, or needing attention). */
export function isDeployed(draft: StudioRecipeDraft): boolean {
  return draft.status === "published" || draft.status === "flagged";
}

export function useStudioData(apiBaseUrl: string, bearerToken: string, investigationId: string): StudioData {
  const [pipelines, setPipelines] = useState<StudioRecipeDraft[] | null>(null);
  const [runs, setRuns] = useState<Record<string, ScheduleRunView[]>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const reload = useCallback(() => setGeneration((g) => g + 1), []);

  useEffect(() => {
    let cancelled = false;
    setProblem(null);
    fetchRecipeRegistry(apiBaseUrl, bearerToken, investigationId)
      .then(async (found) => {
        const current = found.filter((r) => r.status !== "superseded");
        if (cancelled) return;
        setPipelines(current);
        const read = await Promise.all(
          current.filter(isDeployed).map(async (r) => {
            try {
              return [r.recipe_id, await fetchRecipeRuns(apiBaseUrl, bearerToken, investigationId, r.recipe_id)] as const;
            } catch {
              return null;
            }
          }),
        );
        if (!cancelled) setRuns(Object.fromEntries(read.filter((entry) => entry !== null)));
      })
      .catch((err: unknown) => {
        if (!cancelled) setProblem(err instanceof Error ? err.message : "The pipelines could not be read.");
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, generation]);

  return { pipelines, runs, problem, reload };
}
