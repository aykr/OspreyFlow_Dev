// Asks the community worker (`communityWorker.ts`) for every node's community, and keeps only the
// latest answer: the working set changes while Louvain runs, and an answer to an older question is
// dropped rather than drawn over a newer one.
import * as Comlink from "comlink";

import { assignCommunities } from "./communities";
import type { CommunityWorkerApi } from "./communityWorker";

export type Assign = (nodeIds: string[], links: [string, string][]) => Promise<Record<string, number>>;

let remote: Comlink.Remote<CommunityWorkerApi> | null = null;

/** The worker's `assign`, started on first use. Where there is no `Worker` (the unit tests' Node),
 * the same function runs in place. */
export function workerAssign(): Assign {
  if (typeof Worker === "undefined") {
    return (nodeIds, links) => Promise.resolve(assignCommunities(nodeIds, links));
  }
  if (!remote) {
    remote = Comlink.wrap<CommunityWorkerApi>(
      new Worker(new URL("./communityWorker.ts", import.meta.url), { type: "module" }),
    );
  }
  const worker = remote;
  return (nodeIds, links) => worker.assign(nodeIds, links);
}

/** A runner that answers only the latest question: `ask` resolves with the assignment, or with
 * `null` when a newer `ask` was made before this one's answer came back. */
export function latestOnly(assign: Assign) {
  let asked = 0;
  return async (nodeIds: string[], links: [string, string][]): Promise<ReadonlyMap<string, number> | null> => {
    const mine = ++asked;
    const answer = await assign(nodeIds, links);
    if (mine !== asked) return null;
    return new Map(Object.entries(answer));
  };
}
