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

  it("rejects a finding beside Accept, writing nothing to the view (owner, 6 October 2026)", async () => {
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
              entity_type: "Endpoint",
              properties: { value_normalised: "Houston" },
              confidence: 0.9,
              status: "pending",
            },
          ],
        },
      },
      "/links/e1/events/ev-1/candidates/c1/reject": { status: 200, body: {} },
    });
    const { onDelta } = mount();
    fireEvent.click(await screen.findByRole("button", { name: "Extract entities" }));
    fireEvent.click(await screen.findByRole("button", { name: /Reject Endpoint · Houston/ }));
    expect(await screen.findByText("Rejected")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Accept Endpoint · Houston/ })).toBeNull();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/candidates/c1/reject"))).toBe(true);
    // Only the extraction's own delta (the email's Document); a rejection draws nothing.
    expect(onDelta).toHaveBeenCalledTimes(1);
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

describe("DocumentReader: held media (ADR-094)", () => {
  const IMAGE: DocumentReaderView = {
    ...EMAIL,
    document_id: "content:1",
    title: "IMG_0001.png",
    text: "",
    truncated: false,
    spans: [],
    sent_at: null,
    sender_id: null,
    recipient_id: null,
    edge_id: null,
    event_id: null,
    media_kind: "image",
    has_file: true,
  };

  function serveMedia(routes: Record<string, { status: number; body: unknown; blob?: Blob }>) {
    // `init` is part of the signature so a call's headers can be read back from `mock.calls`.
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      void init;
      const hit = Object.entries(routes).find(([path]) => String(url).endsWith(path));
      const answer = hit?.[1] ?? { status: 404, body: {} };
      return {
        ok: answer.status < 400,
        status: answer.status,
        json: async () => answer.body,
        blob: async () => answer.blob ?? new Blob(),
      };
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:image-1", revokeObjectURL: () => undefined }));
    return fetchMock;
  }

  function mountHeld(documentId = "content:1") {
    render(
      <DocumentReader
        apiBaseUrl="http://api.test"
        bearerToken="tok"
        investigationId="inv-1"
        documentId={documentId}
        ontology={ONTOLOGY}
        labelOf={(id) => id}
        onClose={vi.fn()}
        onDelta={vi.fn()}
      />,
    );
  }

  it("shows an image Document's picture, fetched with the analyst's token", async () => {
    const fetchMock = serveMedia({
      "/documents/content%3A1/reader": { status: 200, body: IMAGE },
      "/documents/content%3A1/file": { status: 200, body: {}, blob: new Blob(["png"], { type: "image/png" }) },
    });
    mountHeld();
    const img = (await screen.findByRole("img", { name: "IMG_0001.png" })) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe("blob:image-1");
    const fileCall = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/file"));
    expect((fileCall?.[1] as unknown as { headers: Record<string, string> }).headers.Authorization).toBe(
      "Bearer tok",
    );
  });

  it("plays a video Document", async () => {
    serveMedia({
      "/documents/content%3A1/reader": { status: 200, body: { ...IMAGE, title: "clip.mp4", media_kind: "video" } },
      "/documents/content%3A1/file": { status: 200, body: {}, blob: new Blob(["mp4"], { type: "video/mp4" }) },
    });
    mountHeld();
    const video = await screen.findByLabelText("clip.mp4");
    expect(video.tagName).toBe("VIDEO");
  });

  it("extracts from a held Document through the Document routes, and accepts a finding", async () => {
    const fetchMock = serveMedia({
      "/documents/content%3A1/reader": { status: 200, body: IMAGE },
      "/documents/content%3A1/file": { status: 200, body: {}, blob: new Blob(["png"]) },
      "/documents/content%3A1/extract": {
        status: 200,
        body: {
          document_id: "content:1",
          text: "Tomasz WOLSKI beside a van.",
          candidates: [
            { id: "c1", document_id: "content:1", entity_type: "Person", properties: { family_name: "WOLSKI" }, confidence: 0.8, status: "pending" },
          ],
        },
      },
      "/documents/content%3A1/candidates/c1/accept": {
        status: 200,
        body: { node_id: "p1", delta: { seq: 2, op: "add", nodes: [], edges: [] } },
      },
    });
    mountHeld();
    fireEvent.click(await screen.findByRole("button", { name: "Extract entities" }));
    fireEvent.click(await screen.findByRole("button", { name: /Accept Person · WOLSKI/ }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/documents/content%3A1/candidates/c1/accept"))).toBe(true),
    );
  });
});
