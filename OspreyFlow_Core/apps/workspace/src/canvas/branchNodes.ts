export interface BranchRequest {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  nodeIds: string[];
}

export type BranchResult =
  | { ok: true; id: string; name: string }
  | { ok: false; message: string };

/**
 * Sends the chosen nodes to a new case of their own (ADR-084), through
 * `POST /v1/investigations/{id}/branch`. The new case holds those nodes and the links between them;
 * the case on screen is not changed. A refusal is reported, never swallowed, and the message for
 * "nothing to branch" does not say whether the nodes were hidden or absent: the Conduit answers
 * both the same on purpose, so the Glass must not make them distinguishable again.
 */
export async function branchSelection(
  fetcher: typeof fetch,
  req: BranchRequest,
): Promise<BranchResult> {
  if (req.nodeIds.length === 0) {
    return { ok: false, message: "Select at least one node to branch." };
  }
  try {
    const response = await fetcher(
      `${req.apiBaseUrl}/v1/investigations/${req.investigationId}/branch`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${req.bearerToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ node_ids: req.nodeIds }),
      },
    );
    if (response.status === 422) {
      return { ok: false, message: "None of the selected nodes could be branched." };
    }
    if (response.status === 403) {
      return {
        ok: false,
        message: "You need Editor access to this case to branch it into a new tab.",
      };
    }
    if (!response.ok) {
      return {
        ok: false,
        message: `Branching failed (${response.status}). No tab was made — try again.`,
      };
    }
    const body = (await response.json()) as { id?: unknown; name?: unknown };
    if (typeof body.id !== "string" || body.id === "") {
      return { ok: false, message: "Branching got an unexpected reply. No tab is confirmed." };
    }
    return { ok: true, id: body.id, name: typeof body.name === "string" ? body.name : "" };
  } catch (err) {
    return {
      ok: false,
      message: `Branching failed: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}
