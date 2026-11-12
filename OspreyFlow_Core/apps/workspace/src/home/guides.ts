// The guides from Home (ADR-145 Amendment 10): under each card a person's rights open, the guide for
// that place: the user guide under the Glass, the developer guide under the Ingest Studio, the
// administration guide under Admin. Rules and Monitoring has none of its own; the architecture guide is
// not linked. The PDF is the deployment's own, read through `GET /v1/guides/{guide}`, which checks the
// place's rights itself: the link is a convenience, never the gate.
//
// The token goes in a header, never in a URL: the PDF is fetched, then opened in a new tab from a blob
// URL. The tab is opened before the fetch, while the activation still counts as the person's own, so a
// browser's pop-up blocker lets it through, and is closed again if the guide cannot be read.
import type { PlaceId } from "../shell/places";

export type GuideId = "user" | "developer" | "administration";

export const GUIDE_FOR_PLACE: Partial<Record<PlaceId, { id: GuideId; words: string }>> = {
  glass: { id: "user", words: "Read the user guide (PDF)" },
  ingest: { id: "developer", words: "Read the developer guide (PDF)" },
  admin: { id: "administration", words: "Read the administration guide (PDF)" },
};

/** How long a guide's blob URL is kept once its tab has it: long enough for the tab to load the PDF. */
export const BLOB_KEPT_MS = 60_000;

export interface OpenGuideDeps {
  apiBaseUrl: string;
  bearerToken: string;
  fetcher?: typeof fetch;
  /** `window.open`, given so a test can stand a tab in for it. */
  openTab?: () => Window | null;
  createUrl?: (blob: Blob) => string;
  revokeUrl?: (url: string) => void;
  later?: (run: () => void, ms: number) => void;
}

/** Opens a guide in a new tab. Resolves to `null` when it opened, or to words saying why it did not. */
export async function openGuide(guide: GuideId, deps: OpenGuideDeps): Promise<string | null> {
  const fetcher = deps.fetcher ?? ((input, init) => fetch(input, init));
  const tab = (deps.openTab ?? (() => window.open("", "_blank")))();
  const createUrl = deps.createUrl ?? ((blob) => URL.createObjectURL(blob));
  const revokeUrl = deps.revokeUrl ?? ((url) => URL.revokeObjectURL(url));
  const later = deps.later ?? ((run, ms) => void setTimeout(run, ms));
  const fail = (words: string) => {
    tab?.close();
    return words;
  };
  let response: Response;
  try {
    response = await fetcher(`${deps.apiBaseUrl}/v1/guides/${guide}`, {
      headers: { Authorization: `Bearer ${deps.bearerToken}`, Accept: "application/pdf" },
    });
  } catch {
    return fail("The guide could not be read just now. Try again shortly.");
  }
  if (!response.ok) {
    let said: string | null = null;
    try {
      const body = (await response.json()) as { detail?: { message?: unknown } };
      if (typeof body.detail?.message === "string") said = body.detail.message;
    } catch {
      // Not the Conduit's words: said below.
    }
    return fail(said ?? `The guide could not be read (the server answered ${response.status}).`);
  }
  const url = createUrl(await response.blob());
  if (!tab) {
    revokeUrl(url);
    return "Your browser did not open a new tab for the guide. Allow pop-ups for this site, then try again.";
  }
  tab.opener = null;
  tab.location.href = url;
  later(() => revokeUrl(url), BLOB_KEPT_MS);
  return null;
}
