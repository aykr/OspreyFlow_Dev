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
  it("names the three places in order, with the sections ADR-145 decision 1 gives", () => {
    expect(PLACES.map((p) => [p.id, p.name])).toEqual([["glass", "The Glass"], ["ingest", "Ingest Studio"], ["admin", "Admin"]]);
    expect(PLACES[0]!.sections).toEqual(["Case", "Boards", "Monitoring"]);
    expect(PLACES[1]!.sections).toEqual(["1 Model", "2 Sources", "3 Pipelines", "4 Runs"]);
  });

  it("opens each place for any one of its rights and for nothing else", () => {
    for (const place of PLACES) for (const right of place.rights) expect(placesFor(new Set([right]))).toContain(place.id);
    expect(placesFor(new Set(["a_right_nobody_has"]))).toEqual([]);
    // Rights not yet known, or not read: no place is offered on a guess.
    expect(placesFor(null)).toEqual([]);
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

  it("under GOV.UK starts its line with no separator, the place being the banner's title", () => {
    applyBrand("govuk");
    render(<ContextBanner place="glass" sections={[{ id: "case", label: "Case", current: true, onSelect: () => {} }]} datasets={["Prison intel"]} />);
    const content = document.querySelector(".govuk-notification-banner__content")!;
    expect(content.firstElementChild?.className).not.toContain("context-banner__sep");
    expect(content.querySelectorAll(".context-banner__sep").length).toBe(1);
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
  it("draws the Glass's Case · Boards · Monitoring, Boards as coming, and goes to the one chosen", () => {
    const monitoring = vi.fn();
    render(
      <ContextBanner
        place="glass"
        sections={[
          { id: "case", label: "Case", current: true, onSelect: () => {} },
          { id: "boards", label: "Boards", current: false },
          { id: "monitoring", label: "Monitoring", current: false, onSelect: monitoring },
        ]}
      />,
    );
    const nav = within(screen.getByRole("navigation", { name: "In the Glass" }));
    expect(nav.getAllByRole("button").map((b) => b.textContent)).toEqual(["Case", "Boards (coming)", "Monitoring"]);
    expect(nav.getByRole("button", { name: "Case" }).getAttribute("aria-current")).toBe("page");
    expect(nav.getByRole("button", { name: "Boards (coming)" }).getAttribute("aria-disabled")).toBe("true");
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

  it("goes from the Glass to the Studio on the case's data, and back to the case it came from", () => {
    const there = crossLinkFor("glass", ["glass", "ingest"], "Kestrel", ["Prison intel"], go)!;
    expect(there.label).toBe("Open Prison intel in the Ingest Studio ↗");
    const back = crossLinkFor("ingest", ["glass", "ingest"], "Kestrel", ["Prison intel"], go)!;
    expect(back.label).toBe("← Back to case Kestrel in the Glass");
    render(<ContextBanner place="ingest" crossLink={back} />);
    fireEvent.click(screen.getByRole("button", { name: "← Back to case Kestrel in the Glass" }));
    expect(go.toGlass).toHaveBeenCalled();
  });
});
