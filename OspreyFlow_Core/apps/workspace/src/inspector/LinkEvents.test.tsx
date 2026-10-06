// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LinkEvents } from "./LinkEvents";
import { eventsEntryLabel } from "./linkEventsApi";

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

  it("hands an opened email to the full-screen reader, with what the reader needs (ADR-092 Amendment 3)", async () => {
    serve({
      "0": {
        total: 1,
        offset: 0,
        limit: 50,
        events: [{ ...event(1, { truncated: true, excerpt: "A long body" }), direction: "inbound" }],
      },
    });
    const onReadFullScreen = vi.fn();
    mount({ onReadFullScreen });
    fireEvent.click(await screen.findByRole("button", { name: /Subject 1/ }));
    fireEvent.click(screen.getByRole("button", { name: "Read full screen" }));
    expect(onReadFullScreen).toHaveBeenCalledWith({
      document_id: "email:ev-1",
      title: "Subject 1",
      text: "A long body",
      truncated: true,
      spans: [],
      sent_at: "2001-05-11T10:00:00Z",
      // Inbound: the far end sent it, as the Inspector's own From says.
      sender_id: "b",
      recipient_id: "a",
      edge_id: "e1",
      event_id: "ev-1",
    });
  });

  it("offers no full-screen reading where nothing can show it", async () => {
    serve({ "0": { total: 1, offset: 0, limit: 50, events: [event(1)] } });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Subject 1/ }));
    expect(screen.queryByRole("button", { name: "Read full screen" })).toBeNull();
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
  // Which links are email is `linkEventsApi.test.ts`'s, against the node the loader writes.
  it("names the entry by what the events are", () => {
    expect(eventsEntryLabel("emails", 12)).toBe("Show emails (12)");
    expect(eventsEntryLabel("events", 1)).toBe("Show events (1)");
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

  it("Extract entities asks the recogniser; Ask the model to extract asks the model (ADR-098)", async () => {
    const { fetchMock } = serveWithExtraction();
    mount({ onDelta: vi.fn() });
    fireEvent.click(await screen.findByRole("button", { name: /Subject 1/ }));
    fireEvent.click(screen.getByRole("button", { name: "Extract entities" }));
    await screen.findByRole("list", { name: "Entities found" });
    fireEvent.click(screen.getByRole("button", { name: "Ask the model to extract" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/extract"))).toHaveLength(2),
    );
    const bodies = fetchMock.mock.calls
      .filter(([u]) => String(u).endsWith("/extract"))
      .map(([, init]) => JSON.parse(String((init as RequestInit).body)));
    expect(bodies).toEqual([{ using: "recogniser" }, { using: "model" }]);
  });

  it("does not offer extraction where nothing can take the delta", async () => {
    serveWithExtraction();
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Subject 1/ }));
    expect(screen.queryByRole("button", { name: "Extract entities" })).toBeNull();
  });
});

describe("LinkEvents: Put on the canvas (ADR-095 decision 4)", () => {
  /** Answers the list, and the documents write the link menu also sends. */
  function serveWithWrite(write: { status: number; body: unknown }) {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        if (url.includes("/events/documents")) {
          return { ok: write.status === 200, status: write.status, json: async () => write.body };
        }
        return { ok: true, status: 200, json: async () => ({ total: 2, offset: 0, limit: 50, events: [event(2), event(1)] }) };
      }),
    );
    return calls;
  }

  it("writes the emails in the timeline's window as the menu does, and says how many", async () => {
    const delta = { op: "add", seq: 4, nodes: [], edges: [] };
    const calls = serveWithWrite({ status: 200, body: { written: 2, without_text: 0, delta } });
    const onDelta = vi.fn();
    mount({ onDelta, getEventsWindow: () => ({ validFrom: "2001-05-01T00:00:00Z", validTo: null }) });
    fireEvent.click(await screen.findByRole("button", { name: "Put on the canvas" }));
    expect((await screen.findByRole("status")).textContent).toBe("2 emails put on the canvas.");
    const write = calls.find((c) => c.url.includes("/events/documents"))!;
    expect(write.url).toBe("http://api.test/v1/investigations/inv-1/links/e1/events/documents");
    expect(JSON.parse(String(write.init?.body))).toEqual({ window: { valid_from: "2001-05-01T00:00:00Z", valid_to: null } });
    expect(onDelta).toHaveBeenCalledWith(delta);
  });

  it("says when the view would be too full, and adds nothing", async () => {
    serveWithWrite({ status: 413, body: { error: "limit_exceeded", cap_kind: "nodes", cap: 50000, would_be: 50120 } });
    const onDelta = vi.fn();
    mount({ onDelta });
    fireEvent.click(await screen.findByRole("button", { name: "Put on the canvas" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Too many for the canvas/);
    expect(onDelta).not.toHaveBeenCalled();
  });

  it("is offered for phone messages too, and not for events without text", async () => {
    serveWithWrite({ status: 200, body: { written: 0, without_text: 0, delta: null } });
    mount({ noun: "messages", onDelta: vi.fn() });
    expect(await screen.findByRole("button", { name: "Put on the canvas" })).toBeTruthy();
    cleanup();
    mount({ noun: "events", onDelta: vi.fn() });
    await screen.findByText("Events (2)");
    expect(screen.queryByRole("button", { name: "Put on the canvas" })).toBeNull();
  });
});
