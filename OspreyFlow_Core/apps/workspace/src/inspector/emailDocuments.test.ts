// ADR-092: *Show emails* puts the emails inside the brushed window on the canvas as Documents.
// The request carries the window; each refusal says what to do next, never a bare status.
import { afterEach, describe, expect, it, vi } from "vitest";

import { emailsOutcomeText, showEmailsAsDocuments } from "./emailDocuments";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);
afterEach(() => fetchMock.mockReset());

function answer(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}

describe("showEmailsAsDocuments", () => {
  it("sends the brushed window, or none", async () => {
    answer(200, { written: 2, without_text: 0, delta: { seq: 1, nodes: [], edges: [] } });
    await showEmailsAsDocuments("http://api", "t", "inv 1", "e/1", {
      validFrom: "2001-05-01T00:00:00Z",
      validTo: "2001-05-31T00:00:00Z",
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, { method: string; body: string }];
    expect(url).toBe("http://api/v1/investigations/inv%201/links/e%2F1/events/documents");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      window: { valid_from: "2001-05-01T00:00:00Z", valid_to: "2001-05-31T00:00:00Z" },
    });

    answer(200, { written: 0, without_text: 0, delta: { seq: 2, nodes: [], edges: [] } });
    await showEmailsAsDocuments("http://api", "t", "inv", "e", null);
    const second = fetchMock.mock.calls[1] as [string, { body: string }];
    expect(JSON.parse(second[1].body)).toEqual({ window: null });
  });

  it("says how far past the cap it would go and what to do", async () => {
    answer(409, { error: "limit_exceeded", cap_kind: "nodes", cap: 50000, would_be: 61234 });
    await expect(showEmailsAsDocuments("http://api", "t", "inv", "e", null)).rejects.toThrow(
      "Too many for the canvas: 61,234 nodes against a limit of 50,000. Narrow the timeline and try again.",
    );
  });

  it("says when the link's events are not documents", async () => {
    answer(422, { error: "not_documents" });
    await expect(showEmailsAsDocuments("http://api", "t", "inv", "e", null)).rejects.toThrow(
      "These events have no text, so none can be shown as a document.",
    );
  });
});

describe("emailsOutcomeText", () => {
  it("counts what went onto the canvas and what had no text", () => {
    expect(emailsOutcomeText(3, 0)).toBe("3 emails put on the canvas.");
    expect(emailsOutcomeText(1, 2)).toBe("1 email put on the canvas; 2 events had no text.");
    expect(emailsOutcomeText(0, 0)).toBe("No emails in the timeline's window.");
  });
});
