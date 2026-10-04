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
