export interface RemoveRequest {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  nodeIds: string[];
}

export type RemoveResult =
  | { ok: true; seq: number }
  | { ok: false; message: string };

/**
 * Takes nodes out of the investigation's working set (the view), through the existing
 * `DELETE /v1/investigations/{id}/nodes` route. The records stay in the store and the server
 * records a History step, so this is undoable. A failure is reported, never swallowed: an analyst
 * who believes the view is clear and it is not has been misled.
 */
export async function removeFromWorkingSet(
  fetcher: typeof fetch,
  req: RemoveRequest,
): Promise<RemoveResult> {
  if (req.nodeIds.length === 0) {
    return { ok: false, message: "Nothing to remove." };
  }
  try {
    const response = await fetcher(
      `${req.apiBaseUrl}/v1/investigations/${req.investigationId}/nodes`,
      {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${req.bearerToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ node_ids: req.nodeIds }),
      },
    );
    if (!response.ok) {
      return {
        ok: false,
        message: `Removing nodes failed (${response.status}). Nothing was removed — try again.`,
      };
    }
    const body = (await response.json()) as { seq?: unknown };
    if (typeof body.seq !== "number") {
      return {
        ok: false,
        message: "Removing nodes got an unexpected reply. Nothing is confirmed removed.",
      };
    }
    return { ok: true, seq: body.seq };
  } catch (err) {
    return {
      ok: false,
      message: `Removing nodes failed: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}
