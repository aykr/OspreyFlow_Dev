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

export interface UnauthorisedWatch {
  /** The Conduit's base URL; `""` means the same origin. */
  apiBaseUrl: string;
  /** The token the page is signed in with now; empty while nobody is. */
  getToken: () => string;
  /** Called when the Conduit refuses a request that carried the current token. */
  onUnauthorised: () => void;
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

/** Wraps `globalThis.fetch`; returns a function that puts it back (only if nobody has wrapped it
 * since, so uninstalling never removes someone else's wrapper). */
export function installUnauthorisedWatch(watch: UnauthorisedWatch): () => void {
  const original = globalThis.fetch;
  const wrapped: typeof fetch = async (input, init) => {
    const response = await original(input, init);
    if (response.status === 401) {
      const token = watch.getToken();
      const sent = authorisationOf(input, init);
      if (token && sent === `Bearer ${token}` && urlOf(input).startsWith(watch.apiBaseUrl)) {
        watch.onUnauthorised();
      }
    }
    return response;
  };
  globalThis.fetch = wrapped;
  return () => {
    if (globalThis.fetch === wrapped) globalThis.fetch = original;
  };
}
