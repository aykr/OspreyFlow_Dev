// A stale sign-in, noticed wherever it happens. Every call the page makes to the Conduit with the
// signed-in token goes through `fetch`; if the Conduit answers 401 to one, the sign-in has gone
// stale (the identity provider was restarted, the token expired) and the page must re-sign in the
// same way whichever screen made the call.
//
// Seen on 3 October 2026: after `make refresh` restarted the identity provider the Glass re-signed
// in, but the Ingest Studio and the case menu showed "401" as raw errors, because only the Glass's
// own few calls were wired to the re-sign-in. Wiring each screen would leave the next one to
// forget, so this watches `fetch` itself. Responses are handed back untouched: each screen still
// sees its own error; this only adds the re-sign-in.

//
// Since ADR-050 Amendment 1 (build order step 18b) the token is renewed in the background, and the
// screens keep the token they were given at sign-in: a renewal changes no React state, so no screen
// reloads what it holds or loses what was typed into it. This watch sends the renewed token in place
// of the one a screen holds, to the Conduit only, and a call the Conduit refused while a renewal was
// due is made once more with the renewed token, so the screen sees that answer instead.

export interface UnauthorisedWatch {
  /** The Conduit's base URL; `""` means the same origin. */
  apiBaseUrl: string;
  /** The token the page's screens hold (the one given at sign-in); empty while nobody is signed in. */
  getToken: () => string;
  /** The token to send now: the latest renewal's. Defaults to `getToken`. */
  currentToken?: () => string;
  /** Called when the Conduit refuses a request that carried the page's token, with a copy of the
   * refusal (its words may say why, ADR-148 Amendment 8). Resolving `true` means a renewed token is
   * now in place, and the request is made once more with it. */
  onUnauthorised: (refusal: Response) => void | boolean | Promise<boolean | void>;
}

function authorisationOf(input: RequestInfo | URL, init?: RequestInit): string | null {
  const headers = init?.headers;
  if (headers instanceof Headers) return headers.get("authorization");
  if (Array.isArray(headers)) {
    const found = headers.find(([name]) => name?.toLowerCase() === "authorization");
    return found ? (found[1] ?? null) : null;
  }
  if (headers) {
    for (const [name, value] of Object.entries(headers)) {
      if (name.toLowerCase() === "authorization") return String(value);
    }
    return null;
  }
  if (typeof Request !== "undefined" && input instanceof Request) {
    return input.headers.get("authorization");
  }
  return null;
}

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

/** A body that can be sent a second time as it is: a stream cannot. */
function replayable(input: RequestInfo | URL, init?: RequestInit): boolean {
  if (typeof Request !== "undefined" && input instanceof Request) return input.body === null;
  const body = init?.body;
  return (
    body === undefined ||
    body === null ||
    typeof body === "string" ||
    body instanceof URLSearchParams ||
    (typeof FormData !== "undefined" && body instanceof FormData) ||
    (typeof Blob !== "undefined" && body instanceof Blob) ||
    body instanceof ArrayBuffer ||
    ArrayBuffer.isView(body)
  );
}

/** The same request with another `Authorization` value, its headers otherwise as given. */
function withAuthorisation(
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  authorisation: string,
): [RequestInfo | URL, RequestInit | undefined] {
  if (init?.headers !== undefined || !(typeof Request !== "undefined" && input instanceof Request)) {
    const headers = new Headers(init?.headers);
    headers.set("Authorization", authorisation);
    return [input, { ...init, headers }];
  }
  const headers = new Headers(input.headers);
  headers.set("Authorization", authorisation);
  return [new Request(input, { headers }), init];
}

/** Wraps `globalThis.fetch`; returns a function that puts it back (only if nobody has wrapped it
 * since, so uninstalling never removes someone else's wrapper). */
export function installUnauthorisedWatch(watch: UnauthorisedWatch): () => void {
  const original = globalThis.fetch;
  const current = () => (watch.currentToken ?? watch.getToken)();
  const wrapped: typeof fetch = async (input, init) => {
    const held = watch.getToken();
    const sent = authorisationOf(input, init);
    const ours =
      held !== "" &&
      urlOf(input).startsWith(watch.apiBaseUrl) &&
      (sent === `Bearer ${held}` || sent === `Bearer ${current()}`);
    if (!ours) return original(input, init);
    // Read before the call: a renewal that lands while it is on the way does not count as new.
    const sending = current();
    const replay = replayable(input, init);
    const response = await original(...withAuthorisation(input, init, `Bearer ${sending}`));
    if (response.status !== 401) return response;
    const renewed = await watch.onUnauthorised(response.clone());
    const now = current();
    if (renewed !== true || !replay || now === sending) return response;
    return original(...withAuthorisation(input, init, `Bearer ${now}`));
  };
  globalThis.fetch = wrapped;
  return () => {
    if (globalThis.fetch === wrapped) globalThis.fetch = original;
  };
}
