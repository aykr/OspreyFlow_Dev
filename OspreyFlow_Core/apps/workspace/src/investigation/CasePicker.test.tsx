// @vitest-environment jsdom
//
// The case picker the owner asked for (29 September 2026: "I don't yet see any option for selecting
// the dataset / case"): shown before the workspace opens, listing only what the server lists, with
// a way to create a new case.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  it("lists each case by name with the level the account holds, never an id alone", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });

    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);

    expect(await screen.findByText("Fixture Corp")).toBeTruthy();
    expect(screen.getByText("PaySim mobile money (internal)")).toBeTruthy();
    expect(screen.getByText(/viewer/i)).toBeTruthy();
    expect(screen.getByText(/author/i)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\bc1\b|\bc2\b/);
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
  it("shows the current case by name and switches to another", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: CASES }) });
    const onOpen = vi.fn();
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={onOpen} />);

    const select = (await screen.findByLabelText(/case/i)) as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe("c1"));
    fireEvent.change(select, { target: { value: "c2" } });

    expect(onOpen).toHaveBeenCalledWith("c2");
  });

  it("offers a new case and opens it once created", async () => {
    stubFetch({
      "GET /v1/investigations": () => ({ status: 200, body: CASES }),
      "POST /v1/investigations": () => ({ status: 201, body: { id: "fresh", name: "Another" } }),
    });
    const onOpen = vi.fn();
    render(<CaseSwitcher apiBaseUrl="http://api" bearerToken="t" currentId="c1" onOpen={onOpen} />);
    await screen.findByLabelText(/case/i);

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
    await screen.findByText("Fixture Corp");
    for (const option of screen.getAllByRole("option")) {
      expect((option.textContent ?? "").trim()).not.toBe("");
    }
  });

  it("lists named cases first, then untitled ones, newest first within each", async () => {
    stubFetch({ "GET /v1/investigations": () => ({ status: 200, body: UNNAMED }) });
    render(<CasePicker apiBaseUrl="http://api" bearerToken="t" lastCaseId={null} onOpen={() => undefined} />);
    await screen.findByText("Fixture Corp");
    const labels = screen.getAllByRole("button").map((b) => b.textContent ?? "");
    expect(labels[0]).toBe("Fixture Corp");
    expect(labels[1]).toMatch(/29 Sep 2026/);
    expect(labels[2]).toMatch(/28 Sep 2026/);
  });
});
