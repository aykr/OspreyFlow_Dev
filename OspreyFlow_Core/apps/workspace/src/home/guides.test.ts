// @vitest-environment jsdom
// ADR-145 Amendment 10: a guide is fetched with the person's token in a header, never in a URL, and opened
// in a tab from a blob URL; a refusal is said in the Conduit's own words and its tab closed.
import { describe, expect, it, vi } from "vitest";

import { BLOB_KEPT_MS, GUIDE_FOR_PLACE, openGuide } from "./guides";

function fakeTab() {
  return { opener: {} as unknown, location: { href: "" }, close: vi.fn() } as unknown as Window & { close: ReturnType<typeof vi.fn> };
}

const pdf = () => new Response(new Blob(["%PDF-1.7 synthetic"], { type: "application/pdf" }), { status: 200, headers: { "Content-Type": "application/pdf" } });

describe("openGuide", () => {
  it("fetches the guide with the token in the Authorization header and opens its blob URL in the tab", async () => {
    const fetcher = vi.fn(async () => pdf());
    const tab = fakeTab();
    const later = vi.fn();
    const revokeUrl = vi.fn();
    const said = await openGuide("user", {
      apiBaseUrl: "https://conduit.example", bearerToken: "secret-token", fetcher, openTab: () => tab,
      createUrl: () => "blob:https://glass.example/1", revokeUrl, later,
    });
    expect(said).toBeNull();
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://conduit.example/v1/guides/user");
    expect(url).not.toContain("secret-token");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer secret-token");
    expect(tab.location.href).toBe("blob:https://glass.example/1");
    expect(tab.opener).toBeNull();
    expect(tab.close).not.toHaveBeenCalled();
    // The blob is let go once the tab has had time to load it, not before.
    expect(revokeUrl).not.toHaveBeenCalled();
    expect(later).toHaveBeenCalledWith(expect.any(Function), BLOB_KEPT_MS);
    (later.mock.calls[0]![0] as () => void)();
    expect(revokeUrl).toHaveBeenCalledWith("blob:https://glass.example/1");
  });

  it("says the Conduit's words for a refusal, and closes the tab it opened", async () => {
    const words = "The administration guide opens with Admin, which your roles do not open. Ask an administrator for a role that opens Admin.";
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ detail: { error: "place_required", message: words } }), { status: 403 }));
    const tab = fakeTab();
    const createUrl = vi.fn();
    const said = await openGuide("administration", { apiBaseUrl: "", bearerToken: "t", fetcher, openTab: () => tab, createUrl });
    expect(said).toBe(words);
    expect(tab.close).toHaveBeenCalled();
    expect(createUrl).not.toHaveBeenCalled();
    expect(tab.location.href).toBe("");
  });

  it("says the status when the answer carries no words, and when the Conduit cannot be reached", async () => {
    const tab = fakeTab();
    expect(await openGuide("developer", { apiBaseUrl: "", bearerToken: "t", openTab: () => tab,
      fetcher: async () => new Response("<html>bad gateway</html>", { status: 502 }) })).toBe("The guide could not be read (the server answered 502).");
    expect(await openGuide("developer", { apiBaseUrl: "", bearerToken: "t", openTab: () => tab,
      fetcher: async () => { throw new TypeError("network"); } })).toBe("The guide could not be read just now. Try again shortly.");
    expect(tab.close).toHaveBeenCalledTimes(2);
  }); // prettier-ignore

  it("says so when the browser opened no tab, and keeps no blob", async () => {
    const revokeUrl = vi.fn();
    const said = await openGuide("user", { apiBaseUrl: "", bearerToken: "t", fetcher: async () => pdf(), openTab: () => null,
                                          createUrl: () => "blob:x", revokeUrl }); // prettier-ignore
    expect(said).toMatch(/did not open a new tab/);
    expect(revokeUrl).toHaveBeenCalledWith("blob:x");
  });

  it("gives the Glass, the Studio and Admin a guide each, and Rules and Monitoring none", () => {
    expect(Object.fromEntries(Object.entries(GUIDE_FOR_PLACE).map(([p, g]) => [p, g!.id]))).toEqual({
      glass: "user", ingest: "developer", admin: "administration",
    });
  });
});
