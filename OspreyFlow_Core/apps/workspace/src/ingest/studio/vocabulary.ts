// The words a person reads in the Studio (ADR-140 decision 2, brief §3): a recipe is a pipeline,
// Verify is Test, Publish is Deploy, checks on load are load rules, flagged is "needs attention",
// superseded is "previous version". Routes, YAML keys and stored statuses keep their names; only
// what is shown changes, and it changes here, once.
import type { StudioRecipeDraft } from "../../../../../packages/schemas/generated";

type StudioRecipeStatus = StudioRecipeDraft["status"];

export const STATUS_WORDS: Record<StudioRecipeStatus, string> = {
  draft: "draft",
  published: "deployed",
  flagged: "needs attention",
  superseded: "previous version",
};

/** A status in words; a status this build does not know is shown as stored, never hidden. */
export function statusWords(status: string): string {
  return (STATUS_WORDS as Record<string, string>)[status] ?? status;
}
