// @vitest-environment jsdom
// Admin › Datasets (ADR-145 decision 8, Amendment 4 decision 6; ADR-143 Amendment 2 decisions 1 and 2).
// Red if a field the Conduit did not name for the screen reaches the page, if the warning below two
// approvers is missing, or if a removed case's dry runs are offered for an open one.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Datasets, sizeWords } from "./Datasets";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const DATASET = {
  id: "ds-a", name: "Prison records", owning_unit: "unit-1", egress: "none", highest_marking: null,
  kind: "source", promotion_policy: "second_person_reviews",
};  // prettier-ignore
const AUTHORS = {
  dataset_id: "ds-a", has_home_case: true, team: null,
  people: [{ id: "eng-1", name: "D. Engineer", approves: true }, { id: "adm-2", name: "S. Lead", approves: false }],
};  // prettier-ignore
const CASES = {
  dataset_id: "ds-a",
  cases: [
    { investigation_id: "open-1", name: "Op Kestrel", state: "open", home_case: false, through: null,
      items: 3, links: 2, size_bytes: 700 },
    // A field the screen must never draw, as a response that carried one would hold it.
    { investigation_id: "gone-1", name: "Op Heron", state: "removed", home_case: false, through: null,
      items: 5, links: 4, size_bytes: 50_000, label: "Drawn suspect Kestrel" },
  ],
};  // prettier-ignore

function serve(posts: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(String(url)).pathname.replace("/v1/admin/", "");
      const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;
      if (init?.method === "POST") posts.push(path);
      if (path === "datasets") return ok([DATASET]);
      if (path === "datasets/ds-a/authors") return ok(AUTHORS);
      if (path === "datasets/ds-a/cases") return ok(CASES);
      if (path === "datasets/ds-a/cases/gone-1/merge/dry-run")
        return ok({ investigation_id: "gone-1", action: "merge", items: 5, links: 4, size_bytes: 50_000,
                    would: "Would merge 5 items and 4 links (48.8 kB). Nothing has been written." });  // prettier-ignore
      return ok({});
    }),
  );
}

describe("Datasets", () => {
  it("says a size in bytes, kB or MB", () => {
    expect([sizeWords(700), sizeWords(50_000), sizeWords(3 * 1024 * 1024)]).toEqual(["700 bytes", "48.8 kB", "3.0 MB"]);
  });

  it("shows a dataset's kind, policy, Authors and linked cases as counts, and only removed cases' dry runs", async () => {
    const posts: string[] = [];
    serve(posts);
    render(<Datasets api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    expect(await screen.findByText("Source")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Details for Prison records" }));
    const cases = await screen.findByRole("table", { name: "Cases linked to Prison records" });
    expect(within(cases).getByText("48.8 kB")).toBeTruthy();
    expect(document.body.textContent).not.toContain("Drawn suspect Kestrel");
    expect(screen.queryByRole("button", { name: "Merge Op Kestrel into the dataset (dry run)" })).toBeNull();
    expect(await screen.findByText("Can approve: D. Engineer.")).toBeTruthy();
    expect(screen.getByRole("note").textContent).toContain("Fewer than two people can approve");
    fireEvent.click(screen.getByRole("button", { name: "Merge Op Heron into the dataset (dry run)" }));
    await waitFor(() => expect(posts).toEqual(["datasets/ds-a/cases/gone-1/merge/dry-run"]));
    expect((await screen.findByRole("status")).textContent).toContain("Nothing has been written.");
  });
});
