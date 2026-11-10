// @vitest-environment jsdom
// Admin › Datasets (ADR-145 decision 8, Amendment 4 decision 6; ADR-143 Amendment 2 decisions 1 and 2).
// Red if a field the Conduit did not name for the screen reaches the page, if the warning below two
// approvers is missing, or if a removed case's dry runs are offered for an open one.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Datasets, doneWhere, sizeWords } from "./Datasets";

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

function serve(posts: string[], dataset: object = DATASET, gets: string[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(String(url)).pathname.replace("/v1/admin/", "");
      const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;
      if (init?.method === "POST") posts.push(path);
      else gets.push(path);
      if (path === "datasets") return ok([dataset]);
      if (path === "datasets/ds-a/authors") return ok(AUTHORS);
      if (path === "datasets/ds-a/cases") return ok(CASES);
      if (path === "datasets/ds-a/cases/gone-1/delete/dry-run")
        return ok({ investigation_id: "gone-1", action: "delete", items: 5, links: 4, size_bytes: 50_000,
                    would: "Op Heron's layer holds 5 items and 4 links (48.8 kB). Deleting it withdraws those not promoted; promoted items are never touched. Nothing has been written." });  // prettier-ignore
      if (path === "datasets/ds-a/cases/gone-1/delete" && !posts.includes("refuse-delete"))
        return ok({ investigation_id: "gone-1", words: "The layer was deleted: its items are withdrawn and kept in the audit. Promoted items were not touched." });
      // The real refusal's body for another unit's dataset (app.py's UnknownDatasetEgressError).
      if (path === "datasets/ds-a/cases/gone-1/delete" && posts.includes("refuse-delete"))
        return { ok: false, status: 404, json: async () => ({ error: "dataset_not_found", detail: "There is no such dataset." }) } as Response;
      if (path === "datasets/ds-a/cases/gone-1/merge/dry-run" && posts.includes("refuse"))
        return { ok: false, status: 403, json: async () => ({ error: "not_an_author", right: "investigate",
          detail: "Only one of the dataset's Authors may merge a removed case's layer into it, in the Ingest Studio's 4 Runs: an Author of its home case who holds Investigate." }) } as Response;  // prettier-ignore
      if (path === "datasets/ds-a/cases/gone-1/merge/dry-run")
        return ok({ investigation_id: "gone-1", action: "merge", items: 5, links: 4, size_bytes: 50_000,
                    would: "Would merge 5 items and 4 links (48.8 kB). Nothing has been written." });  // prettier-ignore
      return ok({});
    }),
  );
}

describe("where a removed case's merge or delete is done", () => {
  it("names the Studio's 4 Runs for each action", () => {
    expect(doneWhere("delete")).toBe(
      "You may delete it below; one of the dataset's Authors may also delete it in the Ingest Studio, under 4 Runs.",
    );
  });
});

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
    const said = (await screen.findByRole("status")).textContent ?? "";
    expect(said).toContain("Nothing has been written.");
    // Docs' review (L2.5b): promotion is built, so the words say where the merge itself is done.
    expect(said).toContain("One of the dataset's Authors merges it in the Ingest Studio, under 4 Runs");
    expect(said).not.toContain("arrive with promotion");
    expect(document.body.textContent).not.toMatch(/20\d\d/);
  });

  it("deletes a removed case's layer after its dry run, in the Conduit's words, and reads the cases again", async () => {
    const posts: string[] = [];
    const gets: string[] = [];
    serve(posts, DATASET, gets);
    render(<Datasets api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Details for Prison records" }));
    await screen.findByRole("table", { name: "Cases linked to Prison records" });
    expect(gets.filter((g) => g === "datasets/ds-a/cases")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Delete Op Heron's layer now" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Merge Op Heron into the dataset (dry run)" }));
    await screen.findByRole("status");
    expect(screen.queryByRole("button", { name: "Delete Op Heron's layer now" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Delete Op Heron's layer (dry run)" }));
    expect((await screen.findByRole("status")).textContent).toContain("You may delete it below");
    expect(screen.getByText("It cannot be undone.")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Delete Op Heron's layer now" }));
    expect(await screen.findByText("Op Heron: The layer was deleted: its items are withdrawn and kept in the audit. Promoted items were not touched.")).toBeTruthy();
    expect(posts).toEqual([
      "datasets/ds-a/cases/gone-1/merge/dry-run", "datasets/ds-a/cases/gone-1/delete/dry-run", "datasets/ds-a/cases/gone-1/delete",
    ]);  // prettier-ignore
    expect(screen.queryByRole("button", { name: "Delete Op Heron's layer now" })).toBeNull();
    // The cases are read again, so the row shows what is left (the review's finding 3).
    await waitFor(() => expect(gets.filter((g) => g === "datasets/ds-a/cases")).toHaveLength(2));
    // Focus moves to the words, since the button it was pressed from has gone (not left on the body).
    expect(document.activeElement?.getAttribute("role")).toBe("status");
    expect(document.activeElement?.textContent).toBe(
      "Op Heron: The layer was deleted: its items are withdrawn and kept in the audit. Promoted items were not touched.",
    );
  });

  it("says a refused Delete in the Conduit's words, drops the dry run's counts and reads the cases again", async () => {
    const posts: string[] = ["refuse-delete"];
    const gets: string[] = [];
    serve(posts, DATASET, gets);
    render(<Datasets api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Details for Prison records" }));
    await screen.findByRole("table", { name: "Cases linked to Prison records" });
    fireEvent.click(screen.getByRole("button", { name: "Delete Op Heron's layer (dry run)" }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete Op Heron's layer now" }));
    expect((await screen.findByRole("alert")).textContent).toBe("That dataset is no longer there.");
    expect(screen.queryByRole("button", { name: "Delete Op Heron's layer now" })).toBeNull();
    expect(screen.queryByText(/layer holds 5 items/)).toBeNull();
    await waitFor(() => expect(gets.filter((g) => g === "datasets/ds-a/cases")).toHaveLength(2));
  });

  it("says a refused merge by the roles that may act, never by a person", async () => {
    const posts: string[] = ["refuse"];
    serve(posts);
    render(<Datasets api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Details for Prison records" }));
    await screen.findByRole("table", { name: "Cases linked to Prison records" });
    fireEvent.click(screen.getByRole("button", { name: "Merge Op Heron into the dataset (dry run)" }));
    const said = (await screen.findByRole("alert")).textContent ?? "";
    expect(said).toContain("Only one of the dataset's Authors may merge");
    expect(said).toMatch(/An Author also needs Investigate, which the .* roles have\./);
    expect(said).not.toContain("Ask an administrator");
    for (const person of ["D. Engineer", "S. Lead", "eng-1", "adm-2"]) expect(said).not.toContain(person);
  });

  it("offers a composite neither a promotion policy nor a merge", async () => {
    const posts: string[] = [];
    serve(posts, { ...DATASET, kind: "composite" });
    render(<Datasets api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Details for Prison records" }));
    await screen.findByRole("table", { name: "Cases linked to Prison records" });
    expect(screen.queryByLabelText("Promotion policy for Prison records")).toBeNull();
    expect(screen.queryByRole("button", { name: "Merge Op Heron into the dataset (dry run)" })).toBeNull();
    expect(screen.getByRole("button", { name: "Delete Op Heron's layer (dry run)" })).toBeTruthy();
  });
});
