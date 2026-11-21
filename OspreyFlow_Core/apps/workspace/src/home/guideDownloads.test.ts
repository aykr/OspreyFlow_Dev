// @vitest-environment jsdom
// The browser's half of opening a guide (ADR-145 Amendment 10; ADR-152 R2, PL4 slice D3e): the saved file and the blank
// tab that the shared package's `openGuide` is given, and that it no longer makes itself.
import { afterEach, describe, expect, it, vi } from "vitest";

import { openBlankTab, openGuide, saveAs } from "./guideDownloads";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("saving a guide", () => {
  it("clicks a hidden link that downloads the blob under the guide's own name, then removes it", () => {
    const clicked: { href: string; download: string; rel: string }[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push({ href: this.href, download: this.download, rel: this.rel });
      expect(document.body.contains(this)).toBe(true);
    });
    saveAs("blob:https://glass.example/1", "ospreyflow-user-guide.pdf");
    expect(clicked).toEqual([{ href: "blob:https://glass.example/1", download: "ospreyflow-user-guide.pdf", rel: "noopener" }]);
    expect(document.querySelector("a[download]")).toBeNull();
  });
});

describe("opening a tab", () => {
  it("is the browser's blank tab, opened in a new window", () => {
    const tab = {} as Window;
    const open = vi.fn(() => tab);
    vi.stubGlobal("open", open);
    expect(openBlankTab()).toBe(tab);
    expect(open).toHaveBeenCalledWith("", "_blank");
  });
});

describe("openGuide here", () => {
  const PDF = () => new Response("%PDF-1.7 synthetic", { status: 200, headers: { "Content-Type": "application/pdf" } });
  const base = { apiBaseUrl: "https://conduit.example", bearerToken: "t", createUrl: () => "blob:x", revokeUrl: vi.fn(), later: vi.fn(), every: vi.fn(() => vi.fn()) };

  it("opens the browser's tab when it is given none, as the guide always did", async () => {
    const tab = { opener: {} as unknown, location: { href: "" }, closed: false } as unknown as Window;
    const open = vi.fn(() => tab);
    vi.stubGlobal("open", open);
    expect(await openGuide("user", { ...base, showsPdf: true, fetcher: async () => PDF() })).toBeNull();
    expect(open).toHaveBeenCalledWith("", "_blank");
    expect(tab.location.href).toBe("blob:x");
  });

  it("saves the file with its own download when it is given none and the browser shows no PDFs", async () => {
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const open = vi.fn();
    vi.stubGlobal("open", open);
    expect(await openGuide("developer", { ...base, showsPdf: false, fetcher: async () => PDF() })).toBeNull();
    expect(open).not.toHaveBeenCalled();
    expect(clicked).toHaveBeenCalledTimes(1);
  });

  it("uses the tab it is handed instead of its own", async () => {
    const openTab = vi.fn(() => null);
    const open = vi.fn();
    vi.stubGlobal("open", open);
    const said = await openGuide("user", { ...base, showsPdf: true, openTab, fetcher: async () => PDF() });
    expect(said).not.toBeNull();
    expect(openTab).toHaveBeenCalledTimes(1);
    expect(open).not.toHaveBeenCalled();
  });
});
