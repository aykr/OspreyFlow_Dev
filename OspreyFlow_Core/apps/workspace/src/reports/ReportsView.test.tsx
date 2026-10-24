// @vitest-environment jsdom
// ADR-111: the Reports view — the case's figures for a reader, in words and plain charts. Held rows
// appear only when the server sends them (Editors and above); a report past its bound says so in
// words with its options (rule 2); the period is asked of the server; the feed downloads as CSV.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReportsView } from "./ReportsView";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

const FIGURES = {
  period_weeks: 12, as_of: "2026-10-11", generated_at: "2026-10-11T08:00:00Z", alerts_total: 3,
  alerts_by_week: [
    { week_start: "2026-10-05", typology: "kyc_screening", count: 2 },
    { week_start: "2026-10-05", typology: "document_verification", count: 1 },
  ],
  open_by_age: [
    { label: "under a day", value: 1 }, { label: "1 to 7 days", value: 0 },
    { label: "7 to 30 days", value: 0 }, { label: "over 30 days", value: 0 },
  ],
  outcomes: [
    { typology: "document_verification", open: 1, claimed: 0, true_positive: 0, false_positive: 0 },
    { typology: "kyc_screening", open: 0, claimed: 0, true_positive: 2, false_positive: 0 },
  ],
  held: null,
  kyc: { customers: 2, verified: 1, unverified: 1,
         by_band: [{ label: "low", value: 1 }, { label: "medium", value: 0 }, { label: "high", value: 1 }] },
};  // prettier-ignore

// ADR-126 decision 4: the POLE card's figures, synthetic (rule 9).
const POLE = {
  classes: [
    { pole_class: "person", total: 412, types: [{ entity_type: "Person", count: 400 }, { entity_type: "ThreatActor", count: 12 }] },
    { pole_class: "object", total: 31, types: [{ entity_type: "Vehicle", count: 31 }] },
    { pole_class: "location", total: 0, types: [] },
    { pole_class: "event", total: 7, types: [{ entity_type: "Incident", count: 7 }] },
    { pole_class: "organisation", total: 5, types: [{ entity_type: "Establishment", count: 5 }] },
  ],
  other: [],
  links: 9951,
  counted_at: "2026-10-24T09:05:00Z",
};  // prettier-ignore

function serve(handler: (url: URL) => Response | null = () => null) {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (raw: string) => {
      const url = new URL(raw);
      asked.push(`${url.pathname.replace("/v1/investigations/c1/", "")}${url.search}`);
      return handler(url) ?? json(200, FIGURES);
    }),
  );
  return asked;
}

function place() {
  render(<ReportsView apiBaseUrl="http://x" bearerToken="t" investigationId="c1" canDownload />);
}

describe("the Reports view", () => {
  it("says the figures in words, by typology, age, outcome and KYC", async () => {
    serve();
    place();
    expect(await screen.findByText("3 alerts in the last 12 weeks")).toBeTruthy();
    const outcomes = screen.getByRole("table", { name: "Outcomes by typology" });
    expect(outcomes.textContent).toContain("KYC screening");
    expect(outcomes.textContent).toContain("Unverified customer");
    expect(screen.getByRole("region", { name: "Open alerts by age" }).textContent).toContain("under a day: 1");
    expect(screen.getByRole("region", { name: "Customers by KYC status" }).textContent).toContain("1 verified, 1 unverified");
  });

  it("draws no KYC card for a case the server sends none for (ADR-126)", async () => {
    serve(() => json(200, { ...FIGURES, kyc: null }));
    place();
    await screen.findByText("3 alerts in the last 12 weeks");
    expect(screen.queryByRole("region", { name: "Customers by KYC status" })).toBeNull();
    expect(screen.queryByText(/1 verified, 1 unverified/)).toBeNull();
  });

  it("draws the POLE summary, and no KYC card, for a case whose figures carry only `pole`", async () => {
    serve(() => json(200, { ...FIGURES, kyc: null, pole: POLE }));
    place();
    const card = await screen.findByRole("region", { name: "POLE summary" });
    expect(screen.queryByRole("region", { name: "Customers by KYC status" })).toBeNull();
    expect(within(card).getByText("Links: 9,951")).toBeTruthy();
  });

  it("draws no POLE card when the figures carry none", async () => {
    serve();
    place();
    await screen.findByText("3 alerts in the last 12 weeks");
    expect(screen.queryByRole("region", { name: "POLE summary" })).toBeNull();
    serve(() => json(200, { ...FIGURES, pole: null }));
    cleanup();
    place();
    await screen.findByText("3 alerts in the last 12 weeks");
    expect(screen.queryByRole("region", { name: "POLE summary" })).toBeNull();
    expect(screen.getByRole("region", { name: "Customers by KYC status" })).toBeTruthy();
  });

  it("draws both cards for a mixed case", async () => {
    serve(() => json(200, { ...FIGURES, pole: POLE }));
    place();
    expect(await screen.findByRole("region", { name: "POLE summary" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Customers by KYC status" })).toBeTruthy();
  });

  it("puts each number on its own class, in the five-class order, with the types beneath", async () => {
    serve(() => json(200, { ...FIGURES, kyc: null, pole: POLE }));
    place();
    const card = await screen.findByRole("region", { name: "POLE summary" });
    const classes = within(card).getAllByRole("listitem", { name: /^(Person|Object|Location|Event|Organisation): / });
    expect(classes.map((li) => li.getAttribute("aria-label"))).toEqual([
      "Person: 412", "Object: 31", "Location: 0", "Event: 7", "Organisation: 5",
    ]);
    const person = classes[0]!;
    expect(within(person).getByText("Person: 400")).toBeTruthy();
    expect(within(person).getByText("ThreatActor: 12")).toBeTruthy();
    expect(within(person).queryByText(/Vehicle/)).toBeNull();
    expect(within(classes[1]!).getByText("Vehicle: 31")).toBeTruthy();
    expect(within(classes[1]!).queryByText(/412/)).toBeNull();
    expect(within(classes[2]!).queryAllByRole("listitem")).toHaveLength(0);
    // Not for the period, and said so, with the time the kept counts were taken.
    expect(card.textContent).toContain("Records before resolution, counted at 24 Oct 2026 09:05 UTC; not for the period.");
  });

  it("says Other (not in this ontology) only when the figures hold a type the ontology does not know", async () => {
    serve(() => json(200, { ...FIGURES, kyc: null, pole: POLE }));
    place();
    const plain = await screen.findByRole("region", { name: "POLE summary" });
    expect(within(plain).queryByText(/Other \(not in this ontology\)/)).toBeNull();
    cleanup();
    serve(() => json(200, { ...FIGURES, kyc: null, pole: { ...POLE, other: [{ entity_type: "Gone", count: 3 }, { entity_type: "Alien", count: 1 }] } }));
    place();
    const card = await screen.findByRole("region", { name: "POLE summary" });
    const other = within(card).getByRole("listitem", { name: "Other (not in this ontology): 4" });
    expect(within(other).getByText("Gone: 3")).toBeTruthy();
    expect(within(other).getByText("Alien: 1")).toBeTruthy();
  });

  it("shows held rows only when the server sends them", async () => {
    serve();
    place();
    await screen.findByText("3 alerts in the last 12 weeks");
    expect(screen.queryByRole("region", { name: "Held rows" })).toBeNull();
    cleanup();
    serve(() => json(200, { ...FIGURES, held: { held: 2, released: 1, rejected: 0 } }));
    place();
    expect((await screen.findByRole("region", { name: "Held rows" })).textContent).toContain("2 waiting");
  });

  it("asks the server for the chosen period", async () => {
    const asked = serve();
    place();
    await screen.findByText("3 alerts in the last 12 weeks");
    fireEvent.change(screen.getByLabelText("Period"), { target: { value: "4" } });
    await waitFor(() => expect(asked).toContain("reports?weeks=4"));
  });

  it("says why a report is not drawn, with its options", async () => {
    serve(() => json(409, { error: "limit_exceeded", cap_kind: "alerts", cap: 10000, would_be: 12500,
                            options: ["shorter_period", "fewer_typologies"] }));  // prettier-ignore
    place();
    expect(
      await screen.findByText("This report would count 12,500 alerts, past its limit of 10,000. Choose a shorter period."),
    ).toBeTruthy();
  });

  it("downloads the feed as CSV", async () => {
    const asked = serve((url) =>
      url.pathname.endsWith("/reports/feed") ? new Response("section,label\n", { status: 200 }) : null,
    );
    const created = vi.fn(() => "blob:x");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    place();
    fireEvent.click(await screen.findByRole("button", { name: "Download the figures (CSV)" }));
    await waitFor(() => expect(asked).toContain("reports/feed?weeks=12&format=csv"));
  });
});
