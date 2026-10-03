import { previewCountFrom, type PreviewCount } from "./nodeGestures";

export interface WouldAddRequest {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  nodeId: string;
  /** `null` asks about every relationship type. */
  edgeTypes: string[] | null;
  /** The working set's node count now: the server reports the size *after* the expansion. */
  currentOrder: number;
  /** How many steps out to count; one when not given. */
  depth?: number;
}

/**
 * How many nodes expanding `nodeId` would add, asked of the non-mutating `/expand/preview` route.
 * A question that could not be answered is `"unavailable"`, never a number.
 */
export async function fetchWouldAdd(
  fetcher: typeof fetch,
  req: WouldAddRequest,
): Promise<PreviewCount> {
  try {
    const response = await fetcher(
      `${req.apiBaseUrl}/v1/investigations/${req.investigationId}/expand/preview`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${req.bearerToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          request: {
            node_ids: [req.nodeId],
            depth: req.depth ?? 1,
            edge_types: req.edgeTypes,
          },
        }),
      },
    );
    if (!response.ok) return previewCountFrom({ ok: false }, req.currentOrder);
    const preview = (await response.json()) as { candidate_node_count: number };
    return previewCountFrom(
      { ok: true, candidateNodeCount: preview.candidate_node_count },
      req.currentOrder,
    );
  } catch {
    return previewCountFrom({ ok: false }, req.currentOrder);
  }
}
