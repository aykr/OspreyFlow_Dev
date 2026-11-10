// @vitest-environment jsdom
// The place search's words (`MapControls.tsx`), rule 2: an answer cut short is never told as "none".
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaseGazetteerPanel, PlaceSearch } from "./MapControls";
import type { GazetteerPanelState } from "./gazetteers";

async function ask(answer: { places: never[]; more: boolean }) {
  render(<PlaceSearch search={async () => answer} onGo={() => undefined} />);
  fireEvent.change(screen.getByRole("searchbox", { name: "Find a place" }), {
    target: { value: "cran" },
  });
  await act(async () => {
    fireEvent.submit(screen.getByRole("search", { name: "Find a place" }));
  });
  return screen.getByRole("status").textContent ?? "";
}

afterEach(cleanup);

describe("PlaceSearch", () => {
  it("says no place matched only when the answer was complete", async () => {
    expect(await ask({ places: [], more: false })).toContain(
      "No place called “cran” is in the gazetteer this case reads.",
    );
  });

  it("says more match when the store's first matches held no gazetteer place", async () => {
    const words = await ask({ places: [], more: true });
    expect(words).toContain("More places match “cran” than were looked through");
    expect(words).not.toContain("No place called");
  });
});


// P6: the case's gazetteers beside the place search (ADR-147 Amendment 2, the owner's ruling 6).
const OSM = { dataset_id: "gazetteer-osm-uk", name: "OpenStreetMap places (UK)", added: false };
const REMOVED =
  "The gazetteer is removed: its places stay in this dataset as its own, and the map's place " +
  "search no longer offers them. A re-build no longer refreshes them; adding it again does.";

async function panel(state: GazetteerPanelState, mayChange = true, onChanged = () => undefined) {
  const add = vi.fn(async () => ({ gazetteers: [{ ...OSM, added: true }], said: null }));
  const remove = vi.fn(async () => ({ gazetteers: [OSM], said: REMOVED }));
  await act(async () => {
    render(
      <CaseGazetteerPanel
        load={async () => state}
        add={add}
        remove={remove}
        mayChange={mayChange}
        onChanged={onChanged}
      />,
    );
  });
  const region = screen.getByRole("region", { name: "Gazetteers in this case's dataset" });
  return { add, remove, region };
}

describe("CaseGazetteerPanel", () => {
  it("lists the unit's gazetteers by name, added or not, with no count", async () => {
    const { region } = await panel({
      state: "ready",
      datasetId: "ds-1",
      gazetteers: [OSM, { dataset_id: "gazetteer-os-names", name: "OS Open Names", added: true }],
    });
    const items = within(region).getAllByRole("listitem").map((li) => li.textContent ?? "");
    expect(items[0]).toContain("OpenStreetMap places (UK)");
    expect(items[0]).toContain("not added");
    expect(items[1]).toContain("OS Open Names");
    expect(items[1]).toContain("— added");
    expect(items[1]).not.toContain("not added");
    expect(region.textContent).not.toMatch(/\d/);
    expect(within(region).getByRole("button", { name: "Add OpenStreetMap places (UK)" })).toBeTruthy();
    expect(within(region).getByRole("button", { name: "Remove OS Open Names" })).toBeTruthy();
  });

  it("adds one to the case's dataset, says so, and tells the place search", async () => {
    const onChanged = vi.fn();
    const { add, region } = await panel({ state: "ready", datasetId: "ds-1", gazetteers: [OSM] }, true, onChanged);
    await act(async () => {
      fireEvent.click(within(region).getByRole("button", { name: "Add OpenStreetMap places (UK)" }));
    });
    expect(add).toHaveBeenCalledWith("ds-1", "gazetteer-osm-uk");
    expect(within(region).getByRole("status").textContent).toContain(
      "OpenStreetMap places (UK) is added: its places are copied into this case's dataset",
    );
    expect(within(region).getByRole("button", { name: "Remove OpenStreetMap places (UK)" })).toBeTruthy();
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("removes one and says the Conduit's fixed words, which give no count", async () => {
    const { remove, region } = await panel({
      state: "ready",
      datasetId: "ds-1",
      gazetteers: [{ ...OSM, added: true }],
    });
    await act(async () => {
      fireEvent.click(within(region).getByRole("button", { name: "Remove OpenStreetMap places (UK)" }));
    });
    expect(remove).toHaveBeenCalledWith("ds-1", "gazetteer-osm-uk");
    expect(within(region).getByRole("status").textContent).toContain(REMOVED);
    expect(within(region).getByRole("button", { name: "Add OpenStreetMap places (UK)" })).toBeTruthy();
  });

  it("offers no change to a person without the right, and says what it needs", async () => {
    const { region } = await panel({ state: "ready", datasetId: "ds-1", gazetteers: [OSM] }, false);
    expect(within(region).queryAllByRole("button")).toHaveLength(0);
    expect(region.textContent).toContain(
      "Adding or removing a gazetteer needs the right to run pipelines.",
    );
  });

  it.each([
    ["reads_nothing", "This case reads no dataset yet, so it has no gazetteer to add."],
    ["drawn", "A gazetteer is added to a dataset loaded from sources, and this case reads a drawing"],
    [
      "not_one_source",
      "A gazetteer is added to the one dataset a case reads, and this case reads a composite or more than one",
    ],
    ["none_built", "No gazetteer is built for this case's dataset's unit yet: an administrator builds one in Admin › Maps."],
  ] as const)("shows the panel and says why when %s, in words of its own", async (state, words) => {
    const { region } = await panel({ state });
    expect(region.textContent).toContain(words);
    // The state carries no dataset, so the words cannot name one: no id, no name.
    expect(region.textContent).not.toMatch(/ds-|gazetteer-|OpenStreetMap/);
    expect(within(region).queryAllByRole("button")).toHaveLength(0);
  });

  it("says a failure in the client's words", async () => {
    const { GazetteersFailed } = await import("./gazetteers");
    const add = vi.fn(async () => {
      throw new GazetteersFailed("You may not change this dataset's gazetteers: it needs the right to run pipelines.");
    });
    await act(async () => {
      render(
        <CaseGazetteerPanel
          load={async () => ({ state: "ready", datasetId: "ds-1", gazetteers: [OSM] })}
          add={add}
          remove={vi.fn()}
          mayChange
          onChanged={() => undefined}
        />,
      );
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Add OpenStreetMap places (UK)" }));
    });
    expect(screen.getByRole("region", { name: "Gazetteers in this case's dataset" }).textContent).toContain(
      "You may not change this dataset's gazetteers",
    );
  });
});


describe("CaseGazetteerPanel while a change runs and after", () => {
  it("keeps the pressed button focusable, says it is busy, and ignores a second press", async () => {
    let release: (value: { gazetteers: (typeof OSM)[]; said: null }) => void = () => undefined;
    const add = vi.fn(
      () => new Promise<{ gazetteers: (typeof OSM)[]; said: null }>((resolve) => (release = resolve)),
    );
    await act(async () => {
      render(
        <CaseGazetteerPanel
          load={async () => ({ state: "ready", datasetId: "ds-1", gazetteers: [OSM] })}
          add={add}
          remove={vi.fn()}
          mayChange
          onChanged={() => undefined}
        />,
      );
    });
    const button = screen.getByRole("button", { name: "Add OpenStreetMap places (UK)" });
    button.focus();
    await act(async () => {
      fireEvent.click(button);
    });
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect((button as HTMLButtonElement).disabled).toBe(false);
    expect(document.activeElement).toBe(button);
    await act(async () => {
      fireEvent.click(button);
    });
    expect(add).toHaveBeenCalledTimes(1);
    await act(async () => {
      release({ gazetteers: [{ ...OSM, added: true }], said: null });
    });
    expect(document.activeElement?.getAttribute("aria-label")).toBe("Remove OpenStreetMap places (UK)");
  });

  it("reads the list again after a failed change, so the row says what the Conduit holds", async () => {
    const { GazetteersFailed } = await import("./gazetteers");
    const load = vi
      .fn<() => Promise<GazetteerPanelState>>()
      .mockResolvedValueOnce({ state: "ready", datasetId: "ds-1", gazetteers: [OSM] })
      .mockResolvedValueOnce({ state: "ready", datasetId: "ds-1", gazetteers: [{ ...OSM, added: true }] });
    await act(async () => {
      render(
        <CaseGazetteerPanel
          load={load}
          add={async () => {
            throw new GazetteersFailed("The gazetteer could not be changed (HTTP 500). Try again.");
          }}
          remove={vi.fn()}
          mayChange
          onChanged={() => undefined}
        />,
      );
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Add OpenStreetMap places (UK)" }));
    });
    expect(load).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Remove OpenStreetMap places (UK)" })).toBeTruthy();
  });

  it("shows nothing of the last case while another case's gazetteers are read", async () => {
    const first = async (): Promise<GazetteerPanelState> => ({
      state: "ready",
      datasetId: "ds-1",
      gazetteers: [OSM],
    });
    const second = () => new Promise<GazetteerPanelState>(() => undefined);
    const props = { add: vi.fn(), remove: vi.fn(), mayChange: true, onChanged: () => undefined };
    let rerender: (ui: React.ReactElement) => void = () => undefined;
    await act(async () => {
      rerender = render(<CaseGazetteerPanel load={first} {...props} />).rerender;
    });
    expect(screen.getByRole("button", { name: "Add OpenStreetMap places (UK)" })).toBeTruthy();
    await act(async () => {
      rerender(<CaseGazetteerPanel load={second} {...props} />);
    });
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByText("Reading the gazetteers…")).toBeTruthy();
  });
});

describe("PlaceSearch when the places on offer change", () => {
  it("asks an answer shown again, and asks nothing when none was shown", async () => {
    const search = vi.fn<(query: string) => Promise<{ places: never[]; more: boolean }>>(async () => ({
      places: [],
      more: false,
    }));
    let rerender: (ui: React.ReactElement) => void = () => undefined;
    await act(async () => {
      rerender = render(<PlaceSearch search={search} onGo={() => undefined} asOf={0} />).rerender;
    });
    await act(async () => {
      rerender(<PlaceSearch search={search} onGo={() => undefined} asOf={1} />);
    });
    expect(search).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("searchbox", { name: "Find a place" }), { target: { value: "cran" } });
    await act(async () => {
      fireEvent.submit(screen.getByRole("search", { name: "Find a place" }));
    });
    await act(async () => {
      rerender(<PlaceSearch search={search} onGo={() => undefined} asOf={2} />);
    });
    expect(search.mock.calls.map((call) => call[0])).toEqual(["cran", "cran"]);
  });
});
