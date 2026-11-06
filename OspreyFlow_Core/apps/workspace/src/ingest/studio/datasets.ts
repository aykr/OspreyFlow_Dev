// The Studio opens on a dataset, never a case (ADR-140 decision 1). Until phase 5 gives the Studio
// routes of its own, every Studio route is still a case's (ADR-099 Amendment 4 decision 5), so the
// dataset switcher works through a case of the person's that reads the chosen dataset (ADR-140
// Amendment 2, the owner's ruling "Dataset label, case behind"). A dataset no case of theirs reads
// is not offered: nothing here widens what the person may reach.
import type { AccessLevel, CaseListing } from "../../investigation/cases";

export interface StudioDataset {
  id: string;
  name: string;
}

/** Every dataset one of the person's cases loads into (its first, ADR-099 decision 6), once each,
 * the current case's first, so the one the Studio is open on heads the list. A dataset a case only
 * reads is left out: through that case a load would go into another dataset than the label names. */
export function studioDatasets(cases: readonly CaseListing[], currentId: string | null): StudioDataset[] {
  const ordered = [
    ...cases.filter((c) => c.id === currentId),
    ...cases.filter((c) => c.id !== currentId),
  ];
  const seen = new Map<string, StudioDataset>();
  for (const listing of ordered) {
    const id = listing.dataset_ids?.[0];
    if (id && !seen.has(id)) seen.set(id, { id, name: listing.datasets?.[0] ?? id });
  }
  return [...seen.values()];
}

/** The dataset the Studio is open on: what a load from this case is written into, its first
 * (ADR-099 decision 6). `null` when the case reads none, or is not among the person's cases. */
export function currentDataset(cases: readonly CaseListing[], caseId: string | null): string | null {
  return cases.find((c) => c.id === caseId)?.dataset_ids?.[0] ?? null;
}

const LEVEL_ORDER: Record<AccessLevel, number> = { author: 0, editor: 1, viewer: 2 };

/** The case the Studio works through for `datasetId`. The current case, when the dataset is the one
 * it loads into; otherwise a case of the person's whose first dataset it is (so a load goes where
 * the label says), a case before a branch, the higher level first. `null` when none is. */
export function caseForDataset(
  cases: readonly CaseListing[],
  datasetId: string,
  currentId: string | null,
): string | null {
  if (currentDataset(cases, currentId) === datasetId) return currentId;
  const rank = (c: CaseListing) => [c.branched_from ? 1 : 0, LEVEL_ORDER[c.level]] as const;
  const byRank = (a: CaseListing, b: CaseListing) => {
    const [ab, al] = rank(a);
    const [bb, bl] = rank(b);
    return ab - bb || al - bl || a.name.localeCompare(b.name);
  };
  const loadsInto = cases.filter((c) => c.dataset_ids?.[0] === datasetId).sort(byRank);
  return loadsInto[0]?.id ?? null;
}
