// The Web Worker that finds every node's community for the links between communities (ADR-119),
// off the main thread as spec 02 §5 requires of metrics: on the 50k/250k fixture Louvain takes
// seconds, which on the main thread would hold the first frame it is there to shorten.
import * as Comlink from "comlink";

import { assignCommunities } from "./communities";

export const communityWorkerApi = {
  assign(nodeIds: string[], links: [string, string][]): Record<string, number> {
    return assignCommunities(nodeIds, links);
  },
};

export type CommunityWorkerApi = typeof communityWorkerApi;

Comlink.expose(communityWorkerApi);
