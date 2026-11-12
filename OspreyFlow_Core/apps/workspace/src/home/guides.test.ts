// @vitest-environment jsdom
// ADR-145 Amendment 10: a guide is fetched with the person's token in a header, never in a URL, and shown
// in a tab from a blob URL (or saved under its own name where the browser shows no PDFs); every failure
// is said in words and its tab closed; the promise never rejects.
import { describe, expect, it, vi } from "vitest";

import { GUIDE_FOR_PLACE, SAVED_KEPT_MS, TAB_CHECK_MS, WORDS, openGuide, type OpenGuideDeps } from "./guides";

type FakeTab = Window & { close: ReturnType<typeof vi.fn>; closed: boolean };
function fakeTab(): FakeTab {
  const tab = { opener: {} as unknown, location: { href: "" }, closed: false } as unknown as FakeTab;
  tab.close = vi.fn(() => {
    tab.closed = true;
  });
  return tab;
}

const PDF = "%PDF-1.7 synthetic";
const pdf = (type = "application/pdf", body = PDF) => new Response(body, { status: 200, headers: { "Content-Type": type } });
const deps = (over: Partial<OpenGuideDeps> = {}): OpenGuideDeps => ({
  apiBaseUrl: "https://conduit.example", bearerToken: "secret-token", showsPdf: true,
  createUrl: () => "blob:https://glass.example/1", revokeUrl: vi.fn(), later: vi.fn(), every: vi.fn(() => vi.fn()), ...over,
}); // prettier-ignore

describe("openGuide where the browser shows PDFs", () => {
  it("opens the tab first, fetches with the token in the Authorization header, and shows the PDF from a blob", async () => {
    const order: string[] = [];
    const tab = fakeTab();
    const fetcher = vi.fn(async () => (order.push("fetch"), pdf()));
    let blob: Blob | null = null;
    const said = await openGuide("user", deps({ fetcher, openTab: () => (order.push("tab"), tab), createUrl: (b) => ((blob = b), "blob:x") }));
    expect(said).toBeNull();
    expect(order).toEqual(["tab", "fetch"]);
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://conduit.example/v1/guides/user");
    expect(url).not.toContain("secret-token");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer secret-token");
    expect(blob!.type).toBe("application/pdf");
    expect(tab.location.href).toBe("blob:x");
    expect(tab.opener).toBeNull();
  });

  it("keeps the blob while the tab is open and lets it go once the tab is closed", async () => {
    const tab = fakeTab();
    const revokeUrl = vi.fn();
    let check = () => {};
    const stop = vi.fn();
    const every = vi.fn((run: () => void) => ((check = run), stop));
    await openGuide("user", deps({ fetcher: async () => pdf(), openTab: () => tab, revokeUrl, every }));
    expect(every).toHaveBeenCalledWith(expect.any(Function), TAB_CHECK_MS);
    check();
    expect(revokeUrl).not.toHaveBeenCalled();
    tab.closed = true;
    check();
    expect(revokeUrl).toHaveBeenCalledWith("blob:https://glass.example/1");
    expect(stop).toHaveBeenCalled();
  });

  it("says a blocked pop-up at once, before anything is fetched", async () => {
    const fetcher = vi.fn();
    expect(await openGuide("user", deps({ fetcher, openTab: () => null }))).toBe(WORDS.blocked);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("says the Conduit's words for a refusal, and closes the tab it opened", async () => {
    const words = "The administration guide opens with Admin, which your roles do not open. Ask an administrator for a role that opens Admin.";
    const tab = fakeTab();
    const createUrl = vi.fn();
    const fetcher = async () => new Response(JSON.stringify({ detail: { error: "place_required", message: words } }), { status: 403 });
    expect(await openGuide("administration", deps({ fetcher, openTab: () => tab, createUrl }))).toBe(words);
    expect(tab.close).toHaveBeenCalled();
    expect(createUrl).not.toHaveBeenCalled();
    expect(tab.location.href).toBe("");
  });

  it("words an ended sign-in plainly, and an answer without words by its status", async () => {
    const tab = fakeTab();
    expect(await openGuide("user", deps({ openTab: () => tab, fetcher: async () => new Response("{}", { status: 401 }) }))).toBe(WORDS.signedOut);
    expect(await openGuide("user", deps({ openTab: () => fakeTab(), fetcher: async () => new Response("<html>", { status: 502 }) })))
      .toBe("The guide could not be read (the server answered 502).");
    expect(tab.close).toHaveBeenCalled();
  }); // prettier-ignore

  it("says so when the Conduit cannot be reached, or its body cannot be read, and closes the tab", async () => {
    const reached = fakeTab();
    expect(await openGuide("developer", deps({ openTab: () => reached, fetcher: async () => { throw new TypeError("network"); } }))).toBe(WORDS.unreachable);
    expect(reached.close).toHaveBeenCalled();
    const broken = fakeTab();
    const body = { ok: true, status: 200, headers: new Headers({ "Content-Type": "application/pdf" }), arrayBuffer: async () => { throw new TypeError("aborted"); } } as unknown as Response;
    expect(await openGuide("developer", deps({ openTab: () => broken, fetcher: async () => body }))).toBe(WORDS.unreachable);
    expect(broken.close).toHaveBeenCalled();
  }); // prettier-ignore

  it("refuses an answer that is not a PDF, in words", async () => {
    const tab = fakeTab();
    expect(await openGuide("user", deps({ openTab: () => tab, fetcher: async () => pdf("text/html", "<html>sign in</html>") }))).toBe(WORDS.notPdf);
    expect(tab.close).toHaveBeenCalled();
    // A PDF's bytes under a wrong type are still a PDF.
    expect(await openGuide("user", deps({ openTab: () => fakeTab(), fetcher: async () => pdf("application/octet-stream") }))).toBeNull();
  }); // prettier-ignore

  it("says so when the tab was closed while the guide loaded, and keeps no blob", async () => {
    const tab = fakeTab();
    const revokeUrl = vi.fn();
    const fetcher = async () => ((tab.closed = true), pdf());
    expect(await openGuide("user", deps({ openTab: () => tab, fetcher, revokeUrl }))).toBe(WORDS.closed);
    expect(revokeUrl).toHaveBeenCalledWith("blob:https://glass.example/1");
  });
});

describe("openGuide where the browser shows no PDFs", () => {
  it("opens no tab and saves the PDF under the guide's own name", async () => {
    const openTab = vi.fn();
    const save = vi.fn();
    const later = vi.fn();
    const revokeUrl = vi.fn();
    expect(await openGuide("developer", deps({ showsPdf: false, openTab, save, later, revokeUrl, fetcher: async () => pdf() }))).toBeNull();
    expect(openTab).not.toHaveBeenCalled();
    expect(save).toHaveBeenCalledWith("blob:https://glass.example/1", "ospreyflow-developer-guide.pdf");
    expect(later).toHaveBeenCalledWith(expect.any(Function), SAVED_KEPT_MS);
    (later.mock.calls[0]![0] as () => void)();
    expect(revokeUrl).toHaveBeenCalledWith("blob:https://glass.example/1");
  });
});

describe("the guides' places", () => {
  it("gives the Glass, the Studio and Admin a guide each, and Rules and Monitoring none", () => {
    expect(Object.fromEntries(Object.entries(GUIDE_FOR_PLACE).map(([p, g]) => [p, g!.id]))).toEqual({
      glass: "user", ingest: "developer", admin: "administration",
    });
  });
});
