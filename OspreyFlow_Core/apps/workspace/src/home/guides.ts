// The guides from Home (ADR-145 Amendment 10): under each card a person's rights open, the guide for
// that place: the user guide under the Glass, the developer guide under the Ingest Studio, the
// administration guide under Admin. Rules and Monitoring has none of its own; the architecture guide is
// not linked. The PDF is the deployment's own, read through `GET /v1/guides/{guide}`, which checks the
// place's rights itself: the link is a convenience, never the gate.
//
// The token goes in a header, never in a URL: the PDF is fetched, then shown from a blob URL. Where the
// browser shows PDFs, a tab is opened before the fetch, while the activation still counts as the
// person's own (so a pop-up blocker lets it through), and is sent to the blob once it is read; the blob
// is kept while that tab is open. Where it does not (`navigator.pdfViewerEnabled` false: headless
// Chromium, or a browser set to download PDFs), no tab is opened and the PDF is saved under its own name
// (`ospreyflow-user-guide.pdf`), since a tab sent to a blob would only download it under a random one.
import type { PlaceId } from "../shell/places";

export type GuideId = "user" | "developer" | "administration";

export const GUIDE_FOR_PLACE: Partial<Record<PlaceId, { id: GuideId; words: string }>> = {
  glass: { id: "user", words: "Read the user guide (PDF)" },
  ingest: { id: "developer", words: "Read the developer guide (PDF)" },
  admin: { id: "administration", words: "Read the administration guide (PDF)" },
};

export const GUIDE_FILE: Record<GuideId, string> = {
  user: "ospreyflow-user-guide.pdf",
  developer: "ospreyflow-developer-guide.pdf",
  administration: "ospreyflow-administration-guide.pdf",
};

/** How often a shown guide's tab is checked, to let its blob go once the tab is closed. */
export const TAB_CHECK_MS = 5_000;
/** How long a saved guide's blob is kept: the download has its bytes by then. */
export const SAVED_KEPT_MS = 60_000;

export const WORDS = {
  blocked: "Your browser did not open a new tab for the guide. Allow pop-ups for this site, then try again.",
  unreachable: "The guide could not be read just now. Try again shortly.",
  signedOut: "Your sign-in has ended. Sign in again to read the guide.",
  notPdf: "The guide could not be read: the deployment did not answer with a PDF.",
  closed: "The guide's tab was closed before the guide had loaded.",
} as const;

export function guideUrl(apiBaseUrl: string, guide: GuideId): string {
  return `${apiBaseUrl}/v1/guides/${guide}`;
}

export interface OpenGuideDeps {
  apiBaseUrl: string;
  bearerToken: string;
  fetcher?: typeof fetch;
  /** Whether the browser shows PDFs itself (`navigator.pdfViewerEnabled`). */
  showsPdf?: boolean;
  /** `window.open`, given so a test can stand a tab in for it. */
  openTab?: () => Window | null;
  /** Saves a blob under a name (an `<a download>` clicked), given so a test can stand in for it. */
  save?: (url: string, name: string) => void;
  createUrl?: (blob: Blob) => string;
  revokeUrl?: (url: string) => void;
  later?: (run: () => void, ms: number) => void;
  every?: (run: () => void, ms: number) => () => void;
}

function saveAs(url: string, name: string): void {
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.rel = "noopener";
  link.style.display = "none";
  document.body.append(link);
  link.click();
  link.remove();
}

async function refusalWords(response: Response): Promise<string> {
  if (response.status === 401) return WORDS.signedOut;
  try {
    const body = (await response.json()) as { detail?: { message?: unknown } };
    if (typeof body.detail?.message === "string") return body.detail.message;
  } catch {
    // Not the Conduit's words: said below.
  }
  return `The guide could not be read (the server answered ${response.status}).`;
}

/** Opens a guide. Resolves to `null` when it was shown or saved, or to words saying why it was not;
 * never rejects. */
export async function openGuide(guide: GuideId, deps: OpenGuideDeps): Promise<string | null> {
  const fetcher = deps.fetcher ?? ((input, init) => fetch(input, init));
  const showsPdf = deps.showsPdf ?? navigator.pdfViewerEnabled !== false;
  const createUrl = deps.createUrl ?? ((blob) => URL.createObjectURL(blob));
  const revokeUrl = deps.revokeUrl ?? ((url) => URL.revokeObjectURL(url));
  const later = deps.later ?? ((run, ms) => void setTimeout(run, ms));
  const every =
    deps.every ??
    ((run, ms) => {
      const id = setInterval(run, ms);
      return () => clearInterval(id);
    });
  // The tab first, while the activation still counts as the person's; a blocked one is said at once.
  const tab = showsPdf ? (deps.openTab ?? (() => window.open("", "_blank")))() : null;
  if (showsPdf && !tab) return WORDS.blocked;
  const fail = (words: string) => {
    if (tab && !tab.closed) tab.close();
    return words;
  };
  let url: string | null = null;
  try {
    let response: Response;
    try {
      response = await fetcher(guideUrl(deps.apiBaseUrl, guide), {
        headers: { Authorization: `Bearer ${deps.bearerToken}`, Accept: "application/pdf" },
      });
    } catch {
      return fail(WORDS.unreachable);
    }
    if (!response.ok) return fail(await refusalWords(response));
    const bytes = await response.arrayBuffer();
    const head = new TextDecoder().decode(bytes.slice(0, 5));
    const type = (response.headers.get("Content-Type") ?? "").split(";")[0]!.trim();
    if (type !== "application/pdf" && head !== "%PDF-") return fail(WORDS.notPdf);
    url = createUrl(new Blob([bytes], { type: "application/pdf" }));
    if (!tab) {
      (deps.save ?? saveAs)(url, GUIDE_FILE[guide]);
      const saved = url;
      later(() => revokeUrl(saved), SAVED_KEPT_MS);
      return null;
    }
    if (tab.closed) {
      revokeUrl(url);
      return WORDS.closed;
    }
    tab.opener = null;
    tab.location.href = url;
    tab.opener = null;
    // Kept while the tab is open, so its reload or its own save still find the PDF.
    const shown = url;
    const stop = every(() => {
      if (tab.closed) {
        stop();
        revokeUrl(shown);
      }
    }, TAB_CHECK_MS);
    return null;
  } catch {
    if (url) revokeUrl(url);
    return fail(WORDS.unreachable);
  }
}
