// @vitest-environment jsdom
// ADR-094 step 3, spec 09 §7: the studio's unstructured path is a screen of its own, Files, where
// documents, images and videos are added to the case the studio loads into.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IngestStudio } from "./IngestStudio";

// The Map screen draws with WebGL, which jsdom has not got; this file is about the Files stage.
vi.mock("./map/MapScreen", () => ({ MapScreen: () => null }));
vi.mock("./verify/VerifyScreen", () => ({ VerifyScreen: () => null }));
vi.mock("./publish/PublishScreen", () => ({ PublishScreen: () => null }));
vi.mock("./ProfileScreen", () => ({ ProfileScreen: () => null }));
vi.mock("./ConnectScreen", () => ({ ConnectScreen: () => null }));
vi.mock("../investigation/CaseSwitcher", () => ({ CaseSwitcher: () => null }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("IngestStudio: Files", () => {
  it("offers a Files stage that adds files to the studio's case", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: async () => [] })),
    );
    render(<IngestStudio apiBaseUrl="http://api" bearerToken="t" investigationId="inv-1" onOpenCase={vi.fn()} />);
    fireEvent.click(screen.getByRole("tab", { name: "Files" }));
    expect(await screen.findByRole("region", { name: "Add files" })).toBeTruthy();
    expect(screen.getByText("Add files to the case")).toBeTruthy();
  });

  it("does not offer Files before there is a case to add them to", () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => [] })));
    render(<IngestStudio apiBaseUrl="http://api" bearerToken="t" investigationId={null} onOpenCase={vi.fn()} />);
    expect(screen.queryByRole("tab", { name: "Files" })).toBeNull();
  });
});
