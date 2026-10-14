// @vitest-environment jsdom
// ADR-115 E3 and decision 7: Home after sign-in, every signed-in person's landing with no case open.
// All three places for everyone; one the person cannot use dimmed, with the role it needs; only the
// first usable place's button in brass; G, I and A open them from anywhere on the page.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { HomeSummary } from "./homeData";
import { HomePage } from "./HomePage";

afterEach(cleanup);

const SUMMARY: HomeSummary = {
  glass: [{ tone: "warn", text: "3 alerts in your team's queue, 1 claimed by you" }],
  studio: [{ tone: "warn", text: "2 rows held for review" }],
  admin: [{ tone: "ok", text: "3 of 3 services healthy" }],
  attention: [{ place: "glass", tone: "warn", title: "KYC screening alert in Operation Ledger", detail: "A match. Claimed by you.",
                at: "2026-10-13T06:46:00Z", caseId: "c1" }],  // prettier-ignore
  recent: [{ id: "c1", name: "Operation Ledger", level: "Editor", entities: 68, created: "2026-10-11T09:00:00Z" }],
  services: [{ name: "Graph store", ok: true }],
  held: 2,
};
const PERSON = { username: "osprey-demo-analyst", givenName: "Dana", clearance: "OFFICIAL", roles: ["analyst"] };

function home(rights: string[], props: Partial<Parameters<typeof HomePage>[0]> = {}) {
  const chose = vi.fn();
  const opened = vi.fn();
  render(
    <HomePage rights={new Set(rights)} person={PERSON} summary={SUMMARY} onChoose={chose} onOpenCase={opened}
              account={null} marking="OFFICIAL" now={new Date("2026-10-13T09:00:00Z")} {...props} />,  // prettier-ignore
  );
  return { chose, opened };
}

const panel = (name: string) => within(screen.getByRole("region", { name }));

describe("Home", () => {
  it("greets the person by name and says who they are signed in as", () => {
    home(["investigate"]);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/^Good (morning|afternoon|evening), Dana$/);
    expect(screen.getByText("osprey-demo-analyst").className).toContain("value");
    expect(screen.getByText(/Your roles: Analyst\./)).toBeTruthy();
  });

  it("shows all three places to everyone; one the person cannot use names the role it needs", () => {
    const { chose } = home(["investigate"]);
    expect(screen.getAllByRole("region").map((r) => r.getAttribute("aria-label")).slice(0, 3)).toEqual([
      "Glass", "Ingest Studio", "Admin area",
    ]);
    expect(panel("Ingest Studio").getByText("You need the Data Engineer role for this. Ask an administrator to add it.")).toBeTruthy();
    expect(panel("Admin area").getByText("You need the Admin role for this. Ask an administrator to add it.")).toBeTruthy();
    expect(panel("Ingest Studio").queryByRole("button")).toBeNull();
    fireEvent.click(panel("Glass").getByRole("button", { name: /^Open Glass/ }));
    expect(chose).toHaveBeenCalledWith("glass");
  });

  it("gives brass to the first usable place only", () => {
    home(["investigate", "edit_pipelines", "manage_people"]);
    expect(panel("Glass").getByRole("button", { name: /^Open Glass/ }).className).toContain("btn--primary");
    expect(panel("Ingest Studio").getByRole("button", { name: /^Open Ingest Studio/ }).className).not.toContain("btn--primary");
    expect(panel("Admin area").getByRole("button", { name: /^Open Admin area/ }).className).not.toContain("btn--primary");
  });

  it("opens a usable place with its key from anywhere on the page, and never a gated one", () => {
    const { chose } = home(["investigate", "manage_people"]);
    fireEvent.keyDown(window, { key: "i" });
    expect(chose).not.toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "a" });
    expect(chose).toHaveBeenLastCalledWith("admin");
    fireEvent.keyDown(window, { key: "G" });
    expect(chose).toHaveBeenLastCalledWith("glass");
  });

  it("ignores the keys while typing", () => {
    const { chose } = home(["investigate"]);
    const input = document.createElement("input");
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: "g" });
    expect(chose).not.toHaveBeenCalled();
    input.remove();
  });

  it("lists each place's figures, what needs the person, and their cases", () => {
    const { opened } = home(["investigate", "read_alert_queue"]);
    expect(panel("Glass").getByText("3 alerts in your team's queue, 1 claimed by you")).toBeTruthy();
    const attention = within(screen.getByRole("region", { name: "Needs your attention" }));
    expect(attention.getByText("KYC screening alert in Operation Ledger")).toBeTruthy();
    expect(attention.getByText("1 item")).toBeTruthy();
    fireEvent.click(attention.getByRole("button", { name: /KYC screening alert/ }));
    expect(opened).toHaveBeenCalledWith("c1", "glass");
    const cases = within(screen.getByRole("table", { name: "Recent cases" }));
    expect(cases.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Case", "Your level", "Entities", "Created"]);
    expect(cases.getByText("68").className).toContain("value");
  });

  it("shows only the attention rows of places the person can use", () => {
    home(["edit_pipelines"]);
    expect(screen.queryByText("KYC screening alert in Operation Ledger")).toBeNull();
  });

  it("draws no figure in the picture of a place the person cannot use", () => {
    home(["investigate", "read_held_rows"]);
    expect(panel("Ingest Studio").queryByText(/held/)).toBeNull();
  });

  it("steps through the ways of working, saying which one of four, politely", () => {
    home(["investigate"]);
    const tips = within(screen.getByRole("region", { name: "Ways of working" }));
    expect(tips.getByText("1 of 4")).toBeTruthy();
    expect(tips.getByText("Dim, do not remove")).toBeTruthy();
    fireEvent.click(tips.getByRole("button", { name: "Next way of working" }));
    expect(tips.getByText("Read a link's stroke")).toBeTruthy();
    fireEvent.click(tips.getByRole("button", { name: "Previous way of working" }));
    fireEvent.click(tips.getByRole("button", { name: "Previous way of working" }));
    expect(tips.getByText("4 of 4")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Ways of working" }).querySelector("[aria-live=polite]")).toBeTruthy();
  });

  it("invents nothing it has no source for: no last sign-in, no changelog", () => {
    home(["investigate"]);
    expect(screen.queryByText(/Last sign-in/)).toBeNull();
    expect(screen.queryByText(/^New in/)).toBeNull();
  });

  it("says it is reading while the figures are on their way", () => {
    home(["investigate"], { summary: null });
    expect(panel("Glass").getByText("Reading…")).toBeTruthy();
  });
});
