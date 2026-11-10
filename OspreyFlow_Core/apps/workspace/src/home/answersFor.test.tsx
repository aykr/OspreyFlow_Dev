// @vitest-environment jsdom
// Home's *What you can do, and what you answer for* (ADR-145 Amendment 4 decision 12; L2.7). Red if the
// section lists anything the reader cannot see (a case not theirs, a count of a proposal above their
// clearance), a place their rights do not open, or a *Why* that names anyone but their own roles; or if
// a line does not open where to act.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { NeedsYou } from "../admin/needsYou/needsYouApi";
import type { CaseListing } from "../investigation/cases";
import { answersFor, whyHeld } from "./answersFor";
import { AnswersForSection } from "./AnswersForSection";

afterEach(() => cleanup());

const CASES: CaseListing[] = [
  { id: "c1", name: "Prison intel", level: "author", created_at: "", created_by: "u1" },
  { id: "c2", name: "Op Heron", level: "viewer", created_at: "", created_by: "u9" },
];
const NEEDS: NeedsYou = {
  promotions_overdue: [{ promotion_id: "p1", load_id: "load-7", dataset_id: "ds-a", raised_at: "",
                         words: "Promotion load-7 into Prison records has waited 3 days for review." }],
  proposals: [
    { dataset_id: "ds-a", dataset_name: "Prison records", to_decide: 2 },
  ],
}; // prettier-ignore
const ENGINEER = new Set(["investigate", "edit_pipelines", "review_promotions", "accept_types"]);

describe("answersFor", () => {
  it("lists only the reader's own cases and what waits for them", () => {
    const shown = answersFor({ rights: ENGINEER, roles: ["data_engineer"], cases: CASES, needs: NEEDS });
    expect(shown.levels).toEqual([
      { caseId: "c1", name: "Prison intel", level: "Author" },
      { caseId: "c2", name: "Op Heron", level: "Viewer" },
    ]);
    expect(shown.answers.map((a) => a.text)).toEqual([
      "Author of Prison intel",
      "Reviewer of promotions: Promotion load-7 into Prison records has waited 3 days for review.",
      "Data engineer of Prison records: 2 proposed link types to decide",
    ]);
  });

  it("offers only the places the reader's rights open", () => {
    expect(answersFor({ rights: new Set(["investigate"]), roles: ["analyst"], cases: [], needs: null }).places.map((p) => p.key)).toEqual(["glass"]);
  });

  it("says why by the reader's own roles alone", () => {
    expect(whyHeld("review_promotions", ["data_engineer"])).toBe("Given by your Data Engineer role.");
    expect(whyHeld("read_export_ledger", ["right:read_export_ledger"])).toBe("Given by a right given to you alone.");
    expect(whyHeld("investigate", ["role:r1"])).toBe("Given by a role your administrator made.");
    const can = answersFor({ rights: ENGINEER, roles: ["data_engineer"], cases: [], needs: null }).can.flatMap((g) => g.rights);
    expect(can.map((r) => r.right).sort()).toEqual([...ENGINEER].sort());
  });
});

describe("the Home section", () => {
  it("opens a case, a dataset's Model tab and Operations from what waits, each with its why", async () => {
    const onOpenCase = vi.fn();
    const onOpenModel = vi.fn();
    const onOpenOperations = vi.fn();
    render(
      <AnswersForSection apiBaseUrl="x" bearerToken="t" rights={new Set([...ENGINEER, "operate_schedules"])} roles={["data_engineer"]}
        onOpenCase={onOpenCase} onOpenModel={onOpenModel} onOpenOperations={onOpenOperations}
        read={{ cases: async () => CASES, needs: async () => NEEDS }} />,
    ); // prettier-ignore
    fireEvent.click(await screen.findByRole("button", { name: "Author of Prison intel" }));
    expect(onOpenCase).toHaveBeenCalledWith("c1");
    const model = screen.getByRole("button", { name: "Data engineer of Prison records: 2 proposed link types to decide" });
    expect(document.getElementById(model.getAttribute("aria-describedby")!)?.textContent).toBe("Why: Given by your Data Engineer role.");
    fireEvent.click(model);
    expect(onOpenModel).toHaveBeenCalledWith("ds-a");
    fireEvent.click(screen.getByRole("button", { name: /^Reviewer of promotions/ }));
    expect(onOpenOperations).toHaveBeenCalledOnce();
  });

  it("says a failed read, never nothing", async () => {
    render(
      <AnswersForSection apiBaseUrl="x" bearerToken="t" rights={ENGINEER} roles={["data_engineer"]} onOpenCase={vi.fn()}
        read={{ cases: async () => CASES, needs: async () => { throw new Error("503"); } }} />,
    ); // prettier-ignore
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/Could not read what waits for you/));
  });

  it("says it is reading, then why a line did not open", async () => {
    let release: (n: NeedsYou) => void = () => undefined;
    const pending = new Promise<NeedsYou>((r) => (release = r));
    const onOpenModel = vi.fn(async () => {
      throw new Error("None of your cases loads into that dataset now, so the Studio cannot open on it.");
    });
    render(
      <AnswersForSection apiBaseUrl="x" bearerToken="t" rights={ENGINEER} roles={["data_engineer"]} onOpenCase={vi.fn()}
        onOpenModel={onOpenModel} read={{ cases: async () => [], needs: () => pending }} />,
    ); // prettier-ignore
    expect(await screen.findByText("Reading…")).toBeTruthy();
    expect(screen.queryByText("Nothing waits for you.")).toBeNull();
    release(NEEDS);
    fireEvent.click(await screen.findByRole("button", { name: /2 proposed link types to decide/ }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/None of your cases loads into that dataset/);
  });

  it("says why an administrator answers for a promotion by their Administrator role", () => {
    const shown = answersFor({ rights: new Set(["administer_system"]), roles: ["osprey-admin"], cases: [], needs: NEEDS });
    expect(shown.answers.find((a) => a.text.startsWith("Reviewer"))?.why).toBe("Given by your Administrator role.");
  });
});
