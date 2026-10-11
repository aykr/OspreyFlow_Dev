// @vitest-environment jsdom
// ADR-113 stage 5: what a Reports Viewer reads — the published packs, each item under its own
// marking, read-only, with what is withheld from this reader said by number.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ASSESSMENT_ITEM, NOTE_ITEM, TREND_ITEM, json, serve } from "./reportsTestKit";
import { PublishedTab } from "./PublishedTab";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SUMMARY = { pack_id: "p1", title: "Quarter pack", version: 2, published_at: "2026-10-11T09:00:00Z", published_by: "ana" };
const PUBLISHED = { ...SUMMARY, investigation_id: "c1", items: [TREND_ITEM, ASSESSMENT_ITEM, NOTE_ITEM], withheld: 3, marking: "SECRET" };

function place(canExport = false) {
  serve((c) => (c.path === "published" ? json(200, [SUMMARY]) : c.path === "packs/p1/published" ? json(200, PUBLISHED) : null));
  render(<PublishedTab api={{ apiBaseUrl: "http://x", bearerToken: "t", investigationId: "c1" }} canExport={canExport} />);
}

describe("the Published tab", () => {
  it("lists the published packs by title, version and date", async () => {
    place();
    expect(await screen.findByRole("button", { name: "Quarter pack · Version 2, 11 October 2026" })).toBeTruthy();
  });

  it("says when nothing is published", async () => {
    serve(() => json(200, []));
    render(<PublishedTab api={{ apiBaseUrl: "http://x", bearerToken: "t", investigationId: "c1" }} canExport={false} />);
    expect(await screen.findByText("No pack has been published in this case yet.")).toBeTruthy();
  });

  it("names who published it, or shows the id when the server had no name (ADR-106)", async () => {
    serve((c) => (c.path === "published" ? json(200, [SUMMARY]) : c.path === "packs/p1/published" ? json(200, { ...PUBLISHED, published_by_name: "Ana Ames" }) : null));
    render(<PublishedTab api={{ apiBaseUrl: "http://x", bearerToken: "t", investigationId: "c1" }} canExport={false} />);
    fireEvent.click(await screen.findByRole("button", { name: /Quarter pack/ }));
    expect(await screen.findByText("Version 2, published 11 October 2026 by Ana Ames")).toBeTruthy();
    cleanup();
    place();
    fireEvent.click(await screen.findByRole("button", { name: /Quarter pack/ }));
    expect(await screen.findByText("Version 2, published 11 October 2026 by ana")).toBeTruthy();
  });

  it("shows a chosen pack read-only, with its withheld sentence", async () => {
    place();
    fireEvent.click(await screen.findByRole("button", { name: /Quarter pack/ }));
    expect(await screen.findByText("3 items in this pack are withheld from you.")).toBeTruthy();
    // The pack's own line and the note's banner: two places, each from the server's marking.
    expect(screen.getAllByText("Marked SECRET")).toHaveLength(2);
    expect(screen.getAllByRole("article")).toHaveLength(3);
    for (const name of ["Move up", "Move down", "Remove", "Refresh", "Publish"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.getByRole("article", { name: "Note: Handle with care" }).textContent).toContain("Marked SECRET");
    expect(screen.queryByRole("button", { name: "Export PDF" })).toBeNull();
  });

  it("offers Export PDF to someone who holds the export right", async () => {
    place(true);
    fireEvent.click(await screen.findByRole("button", { name: /Quarter pack/ }));
    expect(await screen.findByRole("button", { name: "Export PDF" })).toBeTruthy();
  });

  it("says nothing of withholding when nothing is withheld", async () => {
    serve((c) => (c.path === "published" ? json(200, [SUMMARY]) : json(200, { ...PUBLISHED, withheld: 0 })));
    render(<PublishedTab api={{ apiBaseUrl: "http://x", bearerToken: "t", investigationId: "c1" }} canExport={false} />);
    fireEvent.click(await screen.findByRole("button", { name: /Quarter pack/ }));
    await screen.findAllByRole("article");
    expect(screen.queryByText(/withheld from you/)).toBeNull();
  });
});
