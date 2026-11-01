// @vitest-environment jsdom
// ADR-133 decision 6, stage (d): the Ingest Studio's "Checks on load" step and Verify's would-be
// alerts. The engineer attaches the case's and the deployment's rules and chooses what a hit does —
// a hold only where the rule runs before commit; a whole-deployment rule applies to every pipeline
// and cannot be left off; nothing here writes a rule (the request carries rule ids and choices
// only). Verify shows the alerts the sample would raise beside the rejections, and each check a dry
// run cannot judge, with why. Synthetic data only (rule 9).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LoadChecksView, VerifyReport } from "../../../../../packages/schemas/generated";
import { WouldRaisePanel } from "../verify/WouldRaisePanel";
import { ChecksScreen, checksToSend, initialChoice } from "./ChecksScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

const VIEW: LoadChecksView = {
  recipe_id: "recipe-1",
  chosen: false,
  checks: [],
  available: [
    { rule_id: "r-case", name: "Listed people", words: "When a Person whose listing is one of sanction, pep, raise a high-severity alert for the case team, after each load commits.",
      scope: "this_case", trigger: "post_commit", severity: "high", status: "active", can_hold: false, always_applies: false, authors_on_hit: "alert" },
    { rule_id: "r-pre", name: "Large cash, before commit", words: "The large cash typology, before each load commits.",
      scope: "this_case", trigger: "pre_commit", severity: "medium", status: "active", can_hold: true, always_applies: false, authors_on_hit: "alert" },
    { rule_id: "r-wide", name: "Sanctions everywhere", words: "When a Person…", scope: "deployment", trigger: "pre_commit",
      severity: "high", status: "active", can_hold: true, always_applies: true, authors_on_hit: "alert" },
  ],
} as unknown as LoadChecksView; // prettier-ignore

describe("the choice", () => {
  it("starts from what is in force: every rule, until someone has chosen", () => {
    const choice = initialChoice(VIEW);
    expect(Object.values(choice).map((c) => c.on)).toEqual([true, true, true]);
    const chosen = initialChoice({ ...VIEW, chosen: true, checks: [{ rule_id: "r-pre", on_hit: "hold" }] });
    expect([chosen["r-case"]!.on, chosen["r-pre"]!.on, chosen["r-pre"]!.onHit, chosen["r-wide"]!.on]).toEqual([false, true, "hold", true]);
  });

  it("sends rule ids and choices only, never a hold on a rule that runs after commit", () => {
    const sent = checksToSend(VIEW, {
      "r-case": { on: true, onHit: "hold" },
      "r-pre": { on: true, onHit: "hold" },
      "r-wide": { on: true, onHit: "alert" },
    });
    expect(sent).toEqual([{ rule_id: "r-case", on_hit: "alert" }, { rule_id: "r-pre", on_hit: "hold" }]);
    for (const check of sent) expect(Object.keys(check).sort()).toEqual(["on_hit", "rule_id"]);
  });
});

describe("the step", () => {
  it("attaches a rule, holds on a hit, and cannot leave off a whole-deployment rule", async () => {
    const calls: { method: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        const body = init?.body ? JSON.parse(String(init.body)) : undefined;
        calls.push({ method, body });
        if (method === "PUT") return json(200, { ...VIEW, chosen: true, checks: (body as { checks: unknown[] }).checks });
        return json(200, VIEW);
      }),
    );
    render(<ChecksScreen apiBaseUrl="http://api" bearerToken="t" investigationId="c1" recipeId="recipe-1" onBack={vi.fn()} />);
    await screen.findByText(/Nothing has been chosen yet/);
    expect((screen.getByLabelText("Apply Sanctions everywhere") as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByLabelText("A hit of Listed people")).toBeNull(); // runs after commit: it cannot hold
    fireEvent.click(screen.getByLabelText("Apply Listed people"));
    fireEvent.change(screen.getByLabelText("A hit of Large cash, before commit"), { target: { value: "hold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the checks" }));
    await screen.findByText(/Saved: 1 rule\(s\) attached/);
    expect(calls.find((c) => c.method === "PUT")!.body).toEqual({ checks: [{ rule_id: "r-pre", on_hit: "hold" }] });
  });

  it("says a refusal in the server's words", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) =>
        (init?.method ?? "GET") === "PUT"
          ? json(422, { detail: { error: "checks_refused", message: "There is no rule “r-gone” in this case to attach." } })
          : json(200, VIEW),
      ),
    );
    render(<ChecksScreen apiBaseUrl="http://api" bearerToken="t" investigationId="c1" recipeId="recipe-1" onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Save the checks" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("There is no rule “r-gone” in this case to attach."));
  });
});

describe("Verify's would-be alerts", () => {
  const REPORT = {
    rows_read: 2, rows_deduplicated: 0, sample_is_whole_source: true, values_masked: false, checks_judged: 2,
    would_raise: [{ rule_id: "r-pre", rule_name: "Large cash, before commit", severity: "medium", on_hit: "hold",
      entity_id: "p1", entity_type: "Person", entity_name: "Okafor" }],
    checks_not_judged: [{ rule_id: "r-link", rule_name: "Linked", why: "It reads links from the stored graph, so it is judged only once the load has committed." }],
  } as unknown as VerifyReport; // prettier-ignore

  it("lists what the sample would raise and what was not judged, and says nothing was written", () => {
    render(<WouldRaisePanel report={REPORT} />);
    expect(screen.getByText(/Nothing was raised, held or written/)).toBeTruthy();
    expect(screen.getByRole("list", { name: "Alerts this sample would raise" }).textContent).toBe(
      "Large cash, before commit · medium severity · Okafor (Person) would hold its rows for review",
    );
    expect(screen.getByRole("list", { name: "Checks a dry run cannot judge" }).textContent).toContain("reads links from the stored graph");
  });

  it("says when no rule checks the pipeline", () => {
    render(<WouldRaisePanel report={{ ...REPORT, checks_judged: 0, would_raise: [], checks_not_judged: [] } as VerifyReport} />);
    expect(screen.getByText("No rule checks this pipeline's loads. Attach rules in Checks on load.")).toBeTruthy();
  });
});
