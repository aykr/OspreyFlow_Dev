// @vitest-environment jsdom
//
// The case picker the owner asked for (29 September 2026: "I don't yet see any option for selecting
// the dataset / case"): shown before the workspace opens, listing only what the server lists, with
// a way to create a new case.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CasePicker } from "./CasePicker";
import { CaseSwitcher } from "./CaseSwitcher";
import { caseLabel, type CaseListing } from "./cases";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CASES: CaseListing[] = [
  { id: "c1", name: "Fixture Corp", level: "author", created_at: "2026-09-29T09:00:00Z", created_by: "a" },
  { id: "c2", name: "PaySim mobile money (internal)", level: "viewer", created_at: "2026-09-28T09:00:00Z", created_by: "b" },
];

function stubFetch(routes: Record<string, () => { status: number; body: unknown }>): ReturnType<typeof vi.fn> {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url.replace("http://api", "")}`;
    const route = routes[key];
    if (!route) throw new Error(`unexpected request ${key}`);
    const { status, body } = route();
    return { ok: status < 300, status, json: async () => body };
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

describe("CasePicker", () => {
  // ADR-114 Amendment 5 point 9: reached from Start, it says what the case is for and goes back.
  it("says what the chosen case is for and has a way back to Start", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    const start = vi.fn();
    render(
      <CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined}
                  title="Choose the case to load into" onStart={start} />,  // prettier-ignore
    );
    expect(screen.getByRole("heading", { name: "Choose the case to load into" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(start).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Fixture Corp")).toBeTruthy();
  });

  it("lists each case by name with the level the account holds, never an id alone", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });

    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);

    expect(await screen.findByText("Fixture Corp")).toBeTruthy();
    expect(screen.getByText("PaySim mobile money (internal)")).toBeTruthy();
    expect(screen.getByText(/viewer/i)).toBeTruthy();
    expect(screen.getByText(/author/i)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\bc1\b|\bc2\b/);
  });

  it("lists each branch beneath the case it came from, said to be a branch (ADR-084 Amendment 3)", async () => {
    const withBranches: CaseListing[] = [
      ...CASES,
      { id: "b1", name: "Fixture Corp · 2 selected", level: "author", created_at: "2026-10-04T09:00:00Z", created_by: "a", branched_from: "c1" },
    ];
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: withBranches }) });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);

    await screen.findByText("Fixture Corp · 2 selected");
    const rows = screen.getAllByRole("listitem").map((row) => row.textContent ?? "");
    const parent = rows.findIndex((text) => text.startsWith("Fixture Corp") && !text.includes("selected"));
    expect(rows[parent + 1]).toMatch(/^Fixture Corp · 2 selected.*branch/);
    const branchRow = screen.getAllByRole("listitem")[parent + 1] as HTMLElement;
    expect(branchRow.dataset.branch).toBe("true");
  });

  it("opens the case that is chosen", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    const onOpen = vi.fn();
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={onOpen} />);

    fireEvent.click(await screen.findByRole("button", { name: /PaySim mobile money/ }));

    expect(onOpen).toHaveBeenCalledWith("c2");
  });

  it("marks the case last opened in this browser", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId="c2" onOpen={() => undefined} />);

    await screen.findByText("Fixture Corp");

    expect(screen.getByText(/last opened/i).closest("li")?.textContent).toContain("PaySim");
  });

  it("says plainly when the account has no cases, and still offers a new one", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: [] }) });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);

    expect(await screen.findByText(/no cases yet/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /create case/i })).toBeTruthy();
  });

  it("creates a named case and opens it", async () => {
    const mock = stubFetch({
      "GET /v1/investigations": () => ({ status: 200, body: [] }),
      "POST /v1/investigations": () => ({ status: 201, body: { id: "fresh", name: "Enron review" } }),
    });
    const onOpen = vi.fn();
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={onOpen} />);
    await screen.findByText(/no cases yet/i);

    fireEvent.change(screen.getByLabelText(/case name/i), { target: { value: "Enron review" } });
    fireEvent.click(screen.getByRole("button", { name: /create case/i }));

    await waitFor(() => expect(onOpen).toHaveBeenCalledWith("fresh"));
    const post = mock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST");
    expect(JSON.parse((post![1] as RequestInit).body as string)).toEqual({ name: "Enron review" });
  });

  it("will not create a case with a blank name", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: [] }) });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);
    await screen.findByText(/no cases yet/i);

    fireEvent.change(screen.getByLabelText(/case name/i), { target: { value: "   " } });

    expect((screen.getByRole("button", { name: /create case/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows the failure when the list cannot be loaded, not an empty picker", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 500, body: {} }) });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText(/no cases yet/i)).toBeNull();
  });
});

describe("CaseSwitcher (the header, and the Ingest Studio)", () => {
  const openMenu = async (name: RegExp = /^Case:/) =>
    fireEvent.click(await screen.findByRole("button", { name }));

  it("shows only the current case's name until it is opened (ADR-065)", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={() => undefined} onBrowse={() => undefined} />);

    const trigger = await screen.findByRole("button", { name: /Case: Fixture Corp/ });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("button", { name: "All cases" })).toBeNull();
    expect(screen.queryByRole("button", { name: "New case" })).toBeNull();
    expect(screen.queryByRole("button", { name: /PaySim/ })).toBeNull();
  });

  it("shows the case's name alone, while its accessible name still says it is the case (ADR-097 step 3)", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={() => undefined} onBrowse={() => undefined} />);
    const trigger = await screen.findByRole("button", { name: /^Case: Fixture Corp/ });
    const visible = trigger.querySelector(".menu-button__label > :not(.visually-hidden)")?.textContent ?? "";
    expect(visible).toBe("Fixture Corp");
    expect(trigger.classList.contains("menu-button--case")).toBe(true);
  });

  it("names the case as 'Current case' until the list arrives, and when it fails", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 500, body: {} }) });
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={() => undefined} />);
    expect(await screen.findByRole("button", { name: /Case: Current case/ })).toBeTruthy();
  });

  it("switches to another case from the opened menu, and closes", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    const onOpen = vi.fn();
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={onOpen} />);

    await screen.findByRole("button", { name: /Case: Fixture Corp/ });
    await openMenu();
    fireEvent.click(screen.getByRole("button", { name: /PaySim mobile money/ }));

    expect(onOpen).toHaveBeenCalledWith("c2");
    expect(screen.queryByRole("group", { name: "Case menu" })).toBeNull();
  });

  it("marks the open case in the menu and does not reopen it", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    const onOpen = vi.fn();
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={onOpen} />);
    await screen.findByRole("button", { name: /Case: Fixture Corp/ });
    await openMenu();

    const current = within(screen.getByRole("group", { name: "Case menu" })).getByRole("button", { name: "Fixture Corp" });
    expect(current.getAttribute("aria-current")).toBe("true");
    fireEvent.click(current);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("offers a new case from the menu and opens it once created", async () => {
    stubFetch({
      "GET /v1/investigations": () => ({ status: 200, body: CASES }),
      "POST /v1/investigations": () => ({ status: 201, body: { id: "fresh", name: "Another" } }),
    });
    const onOpen = vi.fn();
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={onOpen} />);
    await screen.findByRole("button", { name: /Case: Fixture Corp/ });
    await openMenu();

    fireEvent.click(screen.getByRole("button", { name: /new case/i }));
    fireEvent.change(screen.getByLabelText(/new case name/i), { target: { value: "Another" } });
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(onOpen).toHaveBeenCalledWith("fresh"));
  });
});


describe("cases with no name (seen on the owner's deployment: rows with an empty button)", () => {
  const UNNAMED = [
    { id: "u1", name: "", level: "viewer", created_at: "2026-09-29T09:41:00Z", created_by: "a" },
    { id: "u2", name: "   ", level: "viewer", created_at: "2026-09-28T17:05:00Z", created_by: "a" },
    { id: "c1", name: "Fixture Corp", level: "author", created_at: "2026-09-27T09:00:00Z", created_by: "a" },
  ] as const satisfies readonly CaseListing[];

  it("labels a case with no name as untitled, with when it was created, so each row can be told apart", () => {
    expect(caseLabel(UNNAMED[0])).toMatch(/^Untitled case/);
    expect(caseLabel(UNNAMED[0])).toMatch(/29 Sep 2026/);
    expect(caseLabel(UNNAMED[0])).not.toEqual(caseLabel(UNNAMED[1]));
    expect(caseLabel(UNNAMED[2])).toBe("Fixture Corp");
  });

  it("never renders an empty button for a case in the picker or the switcher", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: UNNAMED }) });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);
    await screen.findByText("Fixture Corp");
    for (const button of screen.getAllByRole("button")) {
      expect((button.textContent ?? "").trim()).not.toBe("");
    }
    cleanup();
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: UNNAMED }) });
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: /^Case:/ }));
    await screen.findByRole("button", { name: "Fixture Corp" });
    for (const button of screen.getAllByRole("button")) {
      expect((button.textContent ?? "").trim()).not.toBe("");
    }
  });

  it("lists named cases first, then untitled ones, newest first within each", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: UNNAMED }) });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);
    await screen.findByText("Fixture Corp");
    const labels = screen
      .getAllByRole("button")
      .map((b) => b.textContent ?? "")
      .filter((text) => text !== "Remove");
    expect(labels[0]).toBe("Fixture Corp");
    expect(labels[1]).toMatch(/29 Sep 2026/);
    expect(labels[2]).toMatch(/28 Sep 2026/);
  });
});


describe("removing a case from the picker", () => {
  const MIXED: CaseListing[] = [
    { id: "a1", name: "Mine", level: "author", created_at: "2026-09-29T09:00:00Z", created_by: "me" },
    { id: "e1", name: "Edit only", level: "editor", created_at: "2026-09-28T09:00:00Z", created_by: "x" },
    { id: "v1", name: "View only", level: "viewer", created_at: "2026-09-27T09:00:00Z", created_by: "x" },
  ];

  it("offers Remove only on cases the account is an Author of", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: MIXED }) });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);
    await screen.findByText("Mine");
    expect(screen.getAllByRole("button", { name: /^Remove /i })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Remove Mine" })).toBeTruthy();
  });

  it("offers Remove on every case to an administrator, who may remove a case no Author is left for", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: MIXED }) });
    render(
      <CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} isAdministrator onOpen={() => undefined} />,
    );
    await screen.findByText("Mine");
    expect(screen.getAllByRole("button", { name: /^Remove /i })).toHaveLength(3);
  });

  it("asks once before removing, and Cancel changes nothing", async () => {
    const mock = stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: MIXED }) });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);
    await screen.findByText("Mine");

    fireEvent.click(screen.getByRole("button", { name: "Remove Mine" }));
    expect(screen.getByText(/nothing is deleted/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByText("Mine")).toBeTruthy();
    expect(mock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "DELETE")).toBe(false);
  });

  it("removes the case on confirmation and it leaves the list", async () => {
    const mock = stubFetch({
      "GET /v1/investigations": () => ({ status: 200, body: MIXED }),
      "DELETE /v1/investigations/a1": () => ({ status: 204, body: null }),
    });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);
    await screen.findByText("Mine");

    fireEvent.click(screen.getByRole("button", { name: "Remove Mine" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));

    await waitFor(() => expect(screen.queryByText("Mine")).toBeNull());
    expect(screen.getByText("Edit only")).toBeTruthy();
    expect(mock).toHaveBeenCalledWith("http://api/v1/investigations/a1", expect.objectContaining({ method: "DELETE" }));
  });

  it("keeps the case listed and says why when the server refuses", async () => {
    stubFetch({
      "GET /v1/investigations": () => ({ status: 200, body: MIXED }),
      "DELETE /v1/investigations/a1": () => ({ status: 403, body: null }),
    });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);
    await screen.findByText("Mine");
    fireEvent.click(screen.getByRole("button", { name: "Remove Mine" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("Mine")).toBeTruthy();
  });
});

describe("getting back to the picker (owner: once a case is open there was no way back)", () => {
  it("the switcher offers All cases when it is told how to browse, and not otherwise", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    const onBrowse = vi.fn();
    render(
      <CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={() => undefined} onBrowse={onBrowse} />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /^Case:/ }));
    fireEvent.click(screen.getByRole("button", { name: "All cases" }));
    expect(onBrowse).toHaveBeenCalledTimes(1);

    cleanup();
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: /^Case:/ }));
    expect(screen.queryByRole("button", { name: "All cases" })).toBeNull();
  });

  it("the picker opened over a case offers a way back to it without a reload", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    const onClose = vi.fn();
    render(
      <CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} openCaseId="c1" onClose={onClose} onOpen={() => undefined} />,
    );
    await screen.findByText("Fixture Corp");
    fireEvent.click(screen.getByRole("button", { name: /back to fixture corp/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("offers no way back to a case that has just been removed", async () => {
    stubFetch({
      "GET /v1/investigations": () => ({ status: 200, body: CASES }),
      "DELETE /v1/investigations/c1": () => ({ status: 204, body: null }),
    });
    render(
      <CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} openCaseId="c1" onClose={() => undefined} onOpen={() => undefined} />,
    );
    await screen.findByText("Fixture Corp");
    fireEvent.click(screen.getByRole("button", { name: "Remove Fixture Corp" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await waitFor(() => expect(screen.queryByText("Fixture Corp")).toBeNull());
    expect(screen.queryByRole("button", { name: /^back to/i })).toBeNull();
  });

  it("does not offer a way back when no case is open", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);
    await screen.findByText("Fixture Corp");
    expect(screen.queryByRole("button", { name: /^back to/i })).toBeNull();
  });
});
