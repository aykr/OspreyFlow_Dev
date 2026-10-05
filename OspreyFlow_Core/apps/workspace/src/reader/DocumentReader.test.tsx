// @vitest-environment jsdom
// ADR-092: a Document opens full screen to read. What a mistake here would do, and the case that
// catches it: an email opened blank or without its sender (the first two cases); no way back but
// a mouse (Escape and Close); an email that cannot be extracted from where it is read (Extract).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OntologyRegistry } from "../ontology/schema";
import { DocumentReader } from "./DocumentReader";
import type { DocumentReaderView } from "./readerApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ONTOLOGY = new OntologyRegistry({ version: 1, entity_types: [], edge_types: [] } as never);

const EMAIL: DocumentReaderView = {
  document_id: "email:ev-1",
  title: "Dabhol",
  text: "Dana MERCER wrote about the plant.",
  truncated: true,
  spans: [{ start: 0, end: 11, node_id: "p1", entity_type: "Person", provenance_state: "inferred" }],
  sent_at: "2001-05-14T10:00:00Z",
  sender_id: "a",
  recipient_id: "b",
  edge_id: "e1",
  event_id: "ev-1",
};

function serve(routes: Record<string, { status: number; body: unknown }>) {
  const fetchMock = vi.fn(async (url: string) => {
    const hit = Object.entries(routes).find(([path]) => url.endsWith(path));
    const answer = hit?.[1] ?? { status: 404, body: { error: "document_not_found" } };
    return { ok: answer.status < 400, status: answer.status, json: async () => answer.body };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function mount(onClose = vi.fn(), onDelta = vi.fn()) {
  render(
    <DocumentReader
      apiBaseUrl="http://api.test"
      bearerToken="tok"
      investigationId="inv-1"
      documentId="email:ev-1"
      ontology={ONTOLOGY}
      labelOf={(id) => ({ a: "alice@enron.com", b: "bob@enron.com" })[id] ?? id}
      onClose={onClose}
      onDelta={onDelta}
    />,
  );
  return { onClose, onDelta };
}

describe("DocumentReader", () => {
  it("shows the email's title, sender, recipient, date and full text, and says when it was cut", async () => {
    serve({ "/documents/email%3Aev-1/reader": { status: 200, body: EMAIL } });
    mount();
    const dialog = await screen.findByRole("dialog", { name: "Reading: Dabhol" });
    expect(dialog.textContent).toContain("alice@enron.com");
    expect(dialog.textContent).toContain("bob@enron.com");
    expect(dialog.textContent).toContain("14 May 2001");
    expect(dialog.textContent).toContain("Dana MERCER wrote about the plant.");
    expect(dialog.textContent).toContain("first 4,000 characters");
  });

  it("closes on Escape and on Close, and takes focus to Close when it opens", async () => {
    serve({ "/documents/email%3Aev-1/reader": { status: 200, body: EMAIL } });
    const { onClose } = mount();
    const close = await screen.findByRole("button", { name: "Close" });
    await waitFor(() => expect(document.activeElement).toBe(close));
    fireEvent.keyDown(close, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(close);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("extracts from the email it shows and accepts a finding into the view", async () => {
    const fetchMock = serve({
      "/documents/email%3Aev-1/reader": { status: 200, body: EMAIL },
      "/links/e1/events/ev-1/extract": {
        status: 200,
        body: {
          document_id: "email:ev-1",
          delta: { seq: 2, op: "add", nodes: [], edges: [] },
          candidates: [
            {
              id: "c1",
              document_id: "email:ev-1",
              entity_type: "Person",
              properties: { family_name: "MERCER", given_names: "Dana" },
              confidence: 0.9,
              status: "pending",
            },
          ],
        },
      },
      "/links/e1/events/ev-1/candidates/c1/accept": {
        status: 200,
        body: { node_id: "p1", delta: { seq: 3, op: "add", nodes: [], edges: [] } },
      },
    });
    const { onDelta } = mount();
    fireEvent.click(await screen.findByRole("button", { name: "Extract entities" }));
    fireEvent.click(await screen.findByRole("button", { name: /Accept Person · MERCER, Dana/ }));
    await waitFor(() => expect(onDelta).toHaveBeenCalledTimes(2));
    // The text is read again, so an accepted finding is marked in place.
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/reader"))).toHaveLength(2),
    );
  });

  it("opens on the email it was handed when no Document has been written for it yet", async () => {
    serve({});
    render(
      <DocumentReader
        apiBaseUrl="http://api.test"
        bearerToken="tok"
        investigationId="inv-1"
        documentId="email:ev-1"
        fallback={EMAIL}
        ontology={ONTOLOGY}
        labelOf={(id) => id}
        onClose={vi.fn()}
      />,
    );
    const dialog = await screen.findByRole("dialog", { name: "Reading: Dabhol" });
    expect(dialog.textContent).toContain("Dana MERCER wrote about the plant.");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says when the document is not in the view", async () => {
    serve({});
    mount();
    expect((await screen.findByRole("alert")).textContent).toMatch(/not in your view/);
  });

  it("offers no extraction for a document that is not an email", async () => {
    serve({
      "/documents/email%3Aev-1/reader": {
        status: 200,
        body: { ...EMAIL, edge_id: null, event_id: null, sender_id: null, recipient_id: null },
      },
    });
    mount();
    await screen.findByRole("dialog");
    expect(screen.queryByRole("button", { name: "Extract entities" })).toBeNull();
  });
});
