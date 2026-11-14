// @vitest-environment jsdom
// ADR-145 decisions 1–3: the place switcher shows only the places a person's rights open, the banner
// names the place and the case, and a person holding the Glass and the Studio gets the cross-link.
// That each hidden place's routes refuse the person is `test_place_routes.py`'s, over the same table.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { applyBrand } from "../brand/brand";
import { GovukHeader } from "../brand/govuk/GovukHeader";
import { ContextBanner, crossLinkFor } from "./ContextBanner";
import { PlaceSwitcher } from "./PlaceSwitcher";
import { PLACES, placesFor } from "./places";
import BY_ROLE from "./placesByRole.json";

afterEach(() => {
  cleanup();
  applyBrand("ospreyflow");
});

describe("the places' table", () => {
  it("names the four places in order, with the sections ADR-145 and ADR-146 give", () => {
    expect(PLACES.map((p) => [p.id, p.name])).toEqual([
      ["glass", "The Glass"],
      ["ingest", "Ingest Studio"],
      ["rules", "Rules and Monitoring"],
      ["admin", "Admin"],
    ]);
    // ADR-146 decision 2: Monitoring left the Glass. The Glass's sections are not drawn since ADR-145 Amendment 15
    // (its views are the top bar's view switch); the list stays for the places that still draw theirs.
    expect(PLACES[0]!.sections).toEqual(["Graph", "Drawing board"]);
    expect(PLACES[1]!.sections).toEqual(["1 Model", "2 Sources", "3 Pipelines", "4 Runs"]);
    // The owner's M1: the place's tabs.
    expect(PLACES[2]!.sections).toEqual(["Alerts", "What raises alerts", "Held rows", "Changes"]);
  });

  it("opens each place for any one of its rights, with what it needs, and for nothing else", () => {
    for (const place of PLACES) {
      for (const right of place.rights) expect(placesFor(new Set([right, ...(place.needs ?? [])]))).toContain(place.id);
    }
    expect(placesFor(new Set(["a_right_nobody_has"]))).toEqual([]);
    // Rights not yet known, or not read: no place is offered on a guess.
    expect(placesFor(null)).toEqual([]);
  });

  it("offers Rules and Monitoring only to triage_alerts or author_rules, with the queue's read", () => {
    // ADR-146 decision 2; the queue's read is what its first screen needs (ADR-146 Amendment 2
    // point 5). Red with `needs` not read: a gate right without the queue's read opens it.
    expect(placesFor(new Set(["triage_alerts", "read_alert_queue"]))).toContain("rules");
    expect(placesFor(new Set(["author_rules", "read_alert_queue"]))).toContain("rules");
    expect(placesFor(new Set(["author_rules", "triage_alerts"]))).not.toContain("rules");
    for (const other of ["read_alert_queue", "deploy_rules", "read_held_rows", "decide_held_rows", "read_rule_audit", "load_screening_lists", "keep_watches"]) {
      expect(placesFor(new Set([other, "read_alert_queue"]))).not.toContain("rules");
    }
  });

  // The routes' own answer for every role, legacy role and right granted singly, recorded by the
  // Conduit's place-routes test from the checks each route declares: `placesFor` must agree with it.
  it("offers each role exactly the places the routes answer it in", () => {
    for (const [name, { rights, places }] of Object.entries(BY_ROLE.roles)) {
      expect([name, placesFor(new Set(rights))]).toEqual([name, places]);
    }
    expect(Object.keys(BY_ROLE.roles).length).toBeGreaterThan(50);
  });
});

describe("the place switcher", () => {
  it("lists only the places given, marks the current one, and goes to the one chosen", () => {
    const chose = vi.fn();
    render(<PlaceSwitcher places={placesFor(new Set(["investigate", "edit_pipelines"]))} current="glass" onChoose={chose} />);
    const nav = within(screen.getByRole("navigation", { name: "Places" }));
    expect(nav.getAllByRole("button").map((b) => b.textContent)).toEqual(["The Glass", "Ingest Studio"]);
    expect(nav.getByRole("button", { name: "The Glass" }).getAttribute("aria-current")).toBe("page");
    expect(nav.getByRole("button", { name: "Ingest Studio" }).getAttribute("aria-current")).toBeNull();
    expect(nav.queryByRole("button", { name: "Admin" })).toBeNull();
    fireEvent.click(nav.getByRole("button", { name: "Ingest Studio" }));
    expect(chose).toHaveBeenCalledWith("ingest");
  });

  it("carries the open-alert count on Rules and Monitoring, its count in its name, and none for nothing", () => {
    // ADR-146 decision 2: the count left the Glass's banner for the switcher.
    const { rerender } = render(<PlaceSwitcher places={["glass", "rules"]} current="glass" onChoose={() => {}} counts={{ rules: 3 }} />);
    const nav = within(screen.getByRole("navigation", { name: "Places" }));
    expect(nav.getByRole("button", { name: "Rules and Monitoring 3 open" })).toBeTruthy();
    expect(nav.getByRole("button", { name: "The Glass" })).toBeTruthy();
    rerender(<PlaceSwitcher places={["glass", "rules"]} current="glass" onChoose={() => {}} counts={{ rules: 0 }} />);
    expect(nav.getByRole("button", { name: "Rules and Monitoring" })).toBeTruthy();
  });

  it("draws nothing for a person whose rights open no place", () => {
    render(<PlaceSwitcher places={[]} current={null} onChoose={() => {}} />);
    expect(screen.queryByRole("navigation", { name: "Places" })).toBeNull();
  });

  it("stands inside the GOV.UK header under that brand, and not in the bar", () => {
    applyBrand("govuk");
    render(
      <>
        <GovukHeader withPlaces />
        <div data-testid="bar">
          <PlaceSwitcher places={["glass", "admin"]} current="admin" onChoose={() => {}} />
        </div>
      </>,
    );
    const header = document.querySelector(".govuk-header")!;
    expect(within(header as HTMLElement).getByRole("navigation", { name: "Places" })).toBeTruthy();
    expect(within(screen.getByTestId("bar")).queryByRole("navigation")).toBeNull();
  });
});

describe("the context banner", () => {
  it("says the person is in Rules and Monitoring, with the case it works on", () => {
    render(<ContextBanner place="rules" caseSwitcher={<button type="button">Case Kestrel</button>} />);
    const banner = screen.getByRole("region", { name: "You are in Rules and Monitoring" });
    expect(within(banner).getByRole("button", { name: "Case Kestrel" })).toBeTruthy();
  });

  it("names the place, the case and what it reads in one region", () => {
    render(<ContextBanner place="glass" caseSwitcher={<button type="button">Case Kestrel</button>} datasets={["Prison intel", "Kestrel notes"]} />);
    const banner = screen.getByRole("region", { name: "You are in the Glass" });
    expect(banner.textContent).toContain("reads Prison intel and Kestrel notes");
    expect(within(banner).getByRole("button", { name: "Case Kestrel" })).toBeTruthy();
  });

  it("in the Studio names the case and leaves its dataset to the Studio's own select; in Admin, the place alone", () => {
    render(<ContextBanner place="ingest" caseSwitcher={<button type="button">Case Kestrel</button>} datasets={["Prison intel"]} />);
    // The Studio names its dataset in its own select; the banner does not repeat the case's.
    expect(screen.getByRole("region", { name: "You are in the Ingest Studio" }).textContent).not.toContain("Prison intel");
    cleanup();
    render(<ContextBanner place="admin" />);
    expect(screen.getByRole("region", { name: "You are in Admin" }).textContent).toBe("You are in Admin");
  });

  // ADR-132 Amendment 8: under GOV.UK the banner is one row, its title at the row's start; no title band.
  it("under GOV.UK is one row: the place at its start, as the region's heading and name, then each part set off", () => {
    applyBrand("govuk");
    render(<ContextBanner place="glass" sections={[{ id: "case", label: "Case", current: true, onSelect: () => {} }]} datasets={["Prison intel"]} />);
    const region = screen.getByRole("region", { name: "You are in the Glass" });
    expect(region.querySelector(".govuk-notification-banner__header")).toBeNull();
    const content = region.querySelector(".govuk-notification-banner__content")!;
    expect(content.firstElementChild?.tagName).toBe("H2");
    expect(content.firstElementChild?.textContent).toBe("You are in the Glass");
    expect(content.children[1]?.className).toContain("context-banner__sep");
    expect(content.querySelectorAll(".context-banner__sep").length).toBe(2);
  });

  it("carries Monitoring's open count on its section, said in its name", () => {
    render(<ContextBanner place="glass" sections={[{ id: "monitoring", label: "Monitoring", current: false, onSelect: () => {}, badge: 3 }]} />);
    expect(screen.getByRole("button", { name: "Monitoring 3 open" }).querySelector(".context-banner__badge")?.textContent).toBe("3");
  });

  it("is a GOV.UK notification banner under that brand", () => {
    applyBrand("govuk");
    render(<ContextBanner place="admin" />);
    expect(screen.getByRole("region", { name: "You are in Admin" }).className).toContain("govuk-notification-banner");
  });
});

describe("the banner's sections", () => {
  it("draws each section, one without its screens as coming, and goes to the one chosen", () => {
    const monitoring = vi.fn();
    render(
      <ContextBanner
        place="glass"
        sections={[
          { id: "case", label: "Graph", current: true, onSelect: () => {} },
          { id: "boards", label: "Drawing board", current: false },
          { id: "monitoring", label: "Monitoring", current: false, onSelect: monitoring },
        ]}
      />,
    );
    const nav = within(screen.getByRole("navigation", { name: "In the Glass" }));
    expect(nav.getAllByRole("button").map((b) => b.textContent)).toEqual(["Graph", "Drawing board (coming)", "Monitoring"]);
    expect(nav.getByRole("button", { name: "Graph" }).getAttribute("aria-current")).toBe("page");
    expect(nav.getByRole("button", { name: "Drawing board (coming)" }).getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(nav.getByRole("button", { name: "Monitoring" }));
    expect(monitoring).toHaveBeenCalled();
  });
});

describe("the cross-link", () => {
  const go = { toStudio: vi.fn(), toGlass: vi.fn() };

  it("is offered only to a person who holds both the Glass and the Studio", () => {
    expect(crossLinkFor("glass", ["glass"], "Kestrel", ["Prison intel"], go)).toBeNull();
    expect(crossLinkFor("glass", ["glass", "admin"], "Kestrel", ["Prison intel"], go)).toBeNull();
    expect(crossLinkFor("admin", ["glass", "ingest", "admin"], "Kestrel", null, go)).toBeNull();
  });

  it("goes from the Glass to the Studio on the case's data without naming it again (ADR-145 Amendment 14), and back to the case it came from", () => {
    const there = crossLinkFor("glass", ["glass", "ingest"], "Kestrel", ["Prison intel"], go)!;
    expect(there.label).toBe("Open this case's data in the Ingest Studio ↗");
    const back = crossLinkFor("ingest", ["glass", "ingest"], "Kestrel", ["Prison intel"], go)!;
    expect(back.label).toBe("← Back to case Kestrel in the Glass");
    render(<ContextBanner place="ingest" crossLink={back} />);
    fireEvent.click(screen.getByRole("button", { name: "← Back to case Kestrel in the Glass" }));
    expect(go.toGlass).toHaveBeenCalled();
  });
});
