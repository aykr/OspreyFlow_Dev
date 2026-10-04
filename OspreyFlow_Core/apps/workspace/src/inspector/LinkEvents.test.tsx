// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LinkEvents } from "./LinkEvents";
import { eventsEntryLabel, eventsNoun } from "./linkEventsApi";

// ADR-089. The emails behind a link: newest first as the server orders them, fifty at a time with
// Show more, one opened to read with its cut-off said.

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function event(i: number, over: Record<string, unknown> = {}) {
  return {
    event_id: `ev-${i}`,
    edge_id: "e1",
    edge_type: "COMMUNICATED_WITH",
    source_id: "a",
    target_id: "b",
    occurred_at: `2001-05-${String(10 + i).padStart(2, "0")}T10:00:00Z`,
    direction: "outbound",
    properties: { subject: `Subject ${i}`, excerpt: `Body ${i}`, truncated: false, ...over },
    investigation_scope: "inv-1",
    handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
  };
}

function serve(pages: Record<string, unknown>) {
  const fetchMock = vi.fn(async (url: string) => {
    const offset = new URL(url).searchParams.get("offset") ?? "0";
    const body = pages[offset];
    return { ok: body !== undefined, status: body ? 200 : 404, json: async () => body ?? { error: "link_not_found" } };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function mount(props: Partial<Parameters<typeof LinkEvents>[0]> = {}) {
  render(
    <LinkEvents
      apiBaseUrl="http://api.test"
      bearerToken="tok"
      investigationId="inv-1"
      edgeId="e1"
      noun="emails"
      sourceLabel="alice@enron.com"
      targetLabel="bob@enron.com"
      {...props}
    />,
  );
}

describe("LinkEvents", () => {
  it("lists the emails as the server orders them, with the total in the heading", async () => {
    serve({ "0": { total: 3, offset: 0, limit: 50, events: [event(3), event(2), event(1)] } });
    mount();
    expect(await screen.findByText("Emails (3)")).toBeTruthy();
    const rows = screen.getAllByRole("listitem").map((li) => li.textContent ?? "");
    expect(rows[0]).toContain("Subject 3");
    expect(rows[2]).toContain("Subject 1");
    expect(rows[0]).toContain("alice@enron.com → bob@enron.com");
    expect(screen.queryByRole("button", { name: /Show more/ })).toBeNull();
  });

  it("Show more asks for the next page and appends it", async () => {
    const fetchMock = serve({
      "0": { total: 3, offset: 0, limit: 2, events: [event(3), event(2)] },
      "2": { total: 3, offset: 2, limit: 50, events: [event(1)] },
    });
    mount();
    const more = await screen.findByRole("button", { name: /Show more \(1 left\)/ });
    fireEvent.click(more);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(3));
    expect(String((fetchMock.mock.calls[1] as unknown[])[0])).toContain("offset=2");
    expect(screen.queryByRole("button", { name: /Show more/ })).toBeNull();
  });

  it("opens an email to read, says when it was cut, and goes back to the list", async () => {
    serve({ "0": { total: 1, offset: 0, limit: 50, events: [event(1, { truncated: true, excerpt: "A long body" })] } });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Subject 1/ }));
    const article = screen.getByRole("article", { name: "Email: Subject 1" });
    expect(article.textContent).toContain("A long body");
    expect(article.textContent).toContain("first 4,000 characters");
    expect(article.textContent).toContain("alice@enron.com");
    fireEvent.click(screen.getByRole("button", { name: "Back to the list" }));
    expect(screen.getByRole("list", { name: "Emails" })).toBeTruthy();
  });

  it("says so for a link with no events, and for a link not in the view", async () => {
    serve({ "0": { total: 0, offset: 0, limit: 50, events: [] } });
    mount();
    expect(await screen.findByText(/no dated emails behind it/)).toBeTruthy();
    cleanup();
    serve({});
    mount();
    expect((await screen.findByRole("alert")).textContent).toMatch(/not in your view/);
  });
});

describe("the entry's words", () => {
  it("says emails for a message link between email addresses, events otherwise", () => {
    expect(eventsNoun("COMMUNICATED_WITH", "email")).toBe("emails");
    expect(eventsNoun("COMMUNICATED_WITH", "phone")).toBe("events");
    expect(eventsNoun("PRESENT_AT", "email")).toBe("events");
    expect(eventsEntryLabel("emails", 12)).toBe("Show emails (12)");
  });
});

// ADR-089 step 3: Extract entities on an open email, and accepting one finding at a time.
describe("LinkEvents and extraction", () => {
  function serveWithExtraction() {
    const calls: string[] = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.includes("/extract")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            document_id: "email:ev-1",
            candidates: [
              { id: "c1", document_id: "email:ev-1", entity_type: "Person", properties: { family_name: "MERCER", given_names: "Dana" }, confidence: 0.9, status: "pending" },
              { id: "c2", document_id: "email:ev-1", entity_type: "Organisation", properties: { name: "FERC" }, confidence: 0.6, status: "pending" },
            ],
            delta: { seq: 2, op: "add", nodes: [{ id: "email:ev-1" }], edges: [] },
          }),
        };
      }
      if (url.includes("/accept")) {
        return { ok: true, status: 200, json: async () => ({ node_id: "n-mercer", delta: { seq: 3, op: "add", nodes: [{ id: "n-mercer" }], edges: [] } }) };
      }
      return { ok: true, status: 200, json: async () => ({ total: 1, offset: 0, limit: 50, events: [event(1)] }) };
    });
    vi.stubGlobal("fetch", fetchMock);
    return { fetchMock, calls };
  }

  it("offers Extract entities only when the view can take the delta, lists the findings, and accepts one", async () => {
    const { calls } = serveWithExtraction();
    const onDelta = vi.fn();
    mount({ onDelta });
    fireEvent.click(await screen.findByRole("button", { name: /Subject 1/ }));
    fireEvent.click(screen.getByRole("button", { name: "Extract entities" }));
    const list = await screen.findByRole("list", { name: "Entities found" });
    expect(list.textContent).toContain("Person · MERCER, Dana");
    expect(list.textContent).toContain("90%");
    expect(onDelta).toHaveBeenCalledTimes(1);
    expect(calls.some((c) => c.startsWith("POST") && c.endsWith("/links/e1/events/ev-1/extract"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Accept Person · MERCER, Dana" }));
    await waitFor(() => expect(onDelta).toHaveBeenCalledTimes(2));
    expect(calls.some((c) => c.endsWith("/events/ev-1/candidates/c1/accept"))).toBe(true);
    expect(screen.queryByRole("button", { name: "Accept Person · MERCER, Dana" })).toBeNull();
    expect(screen.getByRole("button", { name: "Accept Organisation · FERC" })).toBeTruthy();
    expect(list.textContent).toContain("Accepted");
  });

  it("does not offer extraction where nothing can take the delta", async () => {
    serveWithExtraction();
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Subject 1/ }));
    expect(screen.queryByRole("button", { name: "Extract entities" })).toBeNull();
  });
});
