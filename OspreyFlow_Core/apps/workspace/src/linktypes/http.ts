// The fetch helper and refusal of every link-type call (ADR-090; ADR-143 decision 9): Bearer auth, and a
// refusal thrown with the server's own sentence and a `kind` the form words its message from. It names
// no path, so importing it says nothing of which place a screen calls (`test_place_routes.py`).
export type LinkTypeErrorKind = "refused" | "not_found" | "forbidden" | "failed";

export class LinkTypeError extends Error {
  kind: LinkTypeErrorKind;
  constructor(kind: LinkTypeErrorKind, message: string) {
    super(message);
    this.name = "LinkTypeError";
    this.kind = kind;
  }
}

async function refusal(response: Response): Promise<LinkTypeError> {
  let body: { error?: string; detail?: string } = {};
  try {
    body = (await response.json()) as typeof body;
  } catch {
    // A non-JSON error body falls through to the generic kinds below.
  }
  if (body.error === "proposal_refused") {
    return new LinkTypeError("refused", body.detail ?? "That cannot be done.");
  }
  if (body.error === "proposal_not_found" || response.status === 404) {
    return new LinkTypeError("not_found", "That proposal is no longer there.");
  }
  if (response.status === 403) return new LinkTypeError("forbidden", "forbidden");
  return new LinkTypeError("failed", `request failed: ${response.status}`);
}

export async function send<T>(url: string, bearerToken: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        Authorization: `Bearer ${bearerToken}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new LinkTypeError("failed", "The server could not be reached.");
  }
  if (!response.ok) throw await refusal(response);
  return (await response.json()) as T;
}
