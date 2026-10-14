// @vitest-environment jsdom
// ADR-115 Amendment 1 point 5, the owner's ruling of 13 October 2026: a case shows a mono scope
// badge beside its name, and its scope is the datasets it reads (ADR-099).
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaseSwitcher } from "./CaseSwitcher";
import { scopeBadge } from "./cases";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("scopeBadge", () => {
  it("names the dataset a case reads, in capitals, and counts any others", () => {
    expect(scopeBadge(["Enron"])).toEqual({ text: "ENRON", title: "This case reads Enron" });
    expect(scopeBadge(["Enron", "Fixture Corp", "PaySim"])).toEqual({
      text: "ENRON +2",
      title: "This case reads Enron, Fixture Corp and PaySim",
    });
  });

  it("says when a case reads no dataset, since it then reads nothing", () => {
    expect(scopeBadge([])).toEqual({ text: "NO DATA", title: "This case reads no dataset" });
  });

  it("shows nothing when the case's datasets are not known", () => {
    expect(scopeBadge(undefined)).toBeNull();
  });
});

describe("the badge beside the case's name", () => {
  it("is drawn from the case listing, in mono, and is not a control", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify([
            { id: "c1", name: "Ledger", level: "author", created_at: "2026-10-01T00:00:00Z", created_by: "a", datasets: ["Enron", "PaySim"] },
          ]),
        ),
      ),
    );
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={() => undefined} />);
    const badge = await screen.findByText("ENRON +1");
    expect(badge.getAttribute("title")).toBe("This case reads Enron and PaySim");
    expect(badge.className).toContain("value");
    expect(badge.closest("button")).toBeNull();
  });
});

// ADR-084 Amendment 4: on a branch the menu's button says where it sits — its case, then the branch —
// and the menu is the same tree as the Cases drawer.
describe("CaseSwitcher on a branch", () => {
  it("names the case, then the branch, and lists the tree", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify([
            { id: "c1", name: "Ledger", level: "author", created_at: "2026-10-01T00:00:00Z", created_by: "a" },
            { id: "b1", name: "Branch of Ledger (2 nodes)", level: "author", created_at: "2026-10-14T16:40:00Z", created_by: "a", branched_from: "c1" },
          ]),
        ),
      ),
    );
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="b1" onOpen={() => undefined} />);
    const button = await screen.findByRole("button", { name: "Case: Ledger › 2 nodes · 14 Oct 16:40" });
    button.click();
    expect(await screen.findByRole("list", { name: "Cases and their branches" })).toBeTruthy();
  });
});
