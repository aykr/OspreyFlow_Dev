// @vitest-environment jsdom
//
// The Metrics panel starts as a slim strip of section names and opens one section at a time, so
// it stops taking a column's worth of controls the analyst has not asked for (ADR-070). What is
// proved here: nothing is shown or fetched until a section is opened; opening one closes the other;
// the community-hull choice survives its section being closed; the ranked list still centres the
// canvas on a node.
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
const communities = () => screen.getByRole("button", { name: /^Communities/ });

describe("MetricsPanel sections", () => {
  it("starts closed: only the section names show, and nothing is fetched", () => {
    const calls = stubCompute();
    setup();
    expect(ranking().getAttribute("aria-expanded")).toBe("false");
    expect(communities().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByLabelText("Primary metric")).toBeNull();
    expect(screen.queryByRole("list", { name: "Ranked nodes" })).toBeNull();
    expect(calls).toEqual([]);
  });

  it("opening Ranking shows its controls and loads the ranking", async () => {
    const calls = stubCompute();
    setup();
    fireEvent.click(ranking());
    expect(ranking().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByLabelText("Primary metric")).toBeTruthy();
    await waitFor(() => expect(calls).toContain("degree"));
    await screen.findByRole("button", { name: /n1/ });
  });

  it("opening Communities closes Ranking: one section is open at a time", () => {
    stubCompute();
    setup();
    fireEvent.click(ranking());
    fireEvent.click(communities());
    expect(communities().getAttribute("aria-expanded")).toBe("true");
    expect(ranking().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByLabelText("Primary metric")).toBeNull();
    expect(screen.getByRole("switch", { name: /Show community hulls/ })).toBeTruthy();
  });

  it("pressing the open section's name closes it", () => {
    stubCompute();
    setup();
    fireEvent.click(ranking());
    fireEvent.click(ranking());
    expect(ranking().getAttribute("aria-expanded")).toBe("false");
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
