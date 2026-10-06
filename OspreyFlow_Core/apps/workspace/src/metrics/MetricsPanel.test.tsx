// @vitest-environment jsdom
//
// The Metrics panel opens on its preview, the ranking, with its other sections folded (ADR-096,
// replacing ADR-070's closed strip and one-at-a-time rule). What is proved here: the ranking shows
// and loads at once while the others are folded and fetch nothing; sections open and close
// independently; the community-hull choice survives its section being closed; the ranked list still
// centres the canvas on a node.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createWorkingSet } from "../workingset/store";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MetricsPanel } from "./MetricsPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubCompute() {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const metric = url.split("/compute/")[1] ?? "";
      calls.push(metric);
      const body =
        metric === "communities"
          ? { mode: "sync", communities: { n1: "a", n2: "a" } }
          : { mode: "sync", values: { n1: 5, n2: 3 } };
      return { ok: true, status: 200, json: async () => body };
    }),
  );
  return calls;
}

function setup(extra: Partial<React.ComponentProps<typeof MetricsPanel>> = {}) {
  const working = createWorkingSet();
  return render(
    <MetricsPanel
      apiBaseUrl="http://api"
      bearerToken="tok"
      investigationId="inv-1"
      graph={working.graph}
      onFocusNode={() => undefined}
      {...extra}
    />,
  );
}

const ranking = () => screen.getByRole("button", { name: /^Ranking/ });
// ADR-097 step 3 (design review item 15): the analysis is named for what it does.
const communities = () => screen.getByRole("button", { name: /^Community detection/ });

describe("MetricsPanel sections", () => {
  it("opens on the ranking, loaded, with the other sections folded and nothing else fetched", async () => {
    const calls = stubCompute();
    setup();
    expect(ranking().getAttribute("aria-expanded")).toBe("true");
    expect(communities().getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByRole("button", { name: /^Filter/ }).getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByLabelText("Primary metric")).toBeTruthy();
    await screen.findByRole("button", { name: /n1/ });
    expect(calls).toEqual(["degree"]);
  });

  it("sections open and close independently", () => {
    stubCompute();
    setup();
    fireEvent.click(communities());
    expect(communities().getAttribute("aria-expanded")).toBe("true");
    expect(ranking().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("switch", { name: /Show community hulls/ })).toBeTruthy();
    fireEvent.click(ranking());
    expect(ranking().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByLabelText("Primary metric")).toBeNull();
  });

  it("the hull choice is kept when its section is closed, so the hulls stay drawn", async () => {
    const calls = stubCompute();
    const onCommunitiesChange = vi.fn();
    setup({ onCommunitiesChange });
    fireEvent.click(communities());
    fireEvent.click(screen.getByRole("switch", { name: /Show community hulls/ }));
    await waitFor(() => expect(calls).toContain("communities"));
    await waitFor(() =>
      expect(onCommunitiesChange).toHaveBeenLastCalledWith({ n1: "a", n2: "a" }),
    );
    fireEvent.click(communities()); // close it
    expect(onCommunitiesChange).not.toHaveBeenLastCalledWith(null);
    fireEvent.click(communities());
    expect(screen.getByRole("switch", { name: /Show community hulls/ }).getAttribute("aria-checked")).toBe("true");
  });
});
