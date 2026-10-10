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
    fireEvent.click(await screen.findByRole("button", { name: "Quick scan" }));
    fireEvent.click(await screen.findByRole("button", { name: /Accept Person · MERCER, Dana/ }));
    await waitFor(() => expect(onDelta).toHaveBeenCalledTimes(2));
    // The text is read again, so an accepted finding is marked in place.
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/reader"))).toHaveLength(2),
    );
  });

  it("accepts all pending findings as one decision and reports refusals in words (ADR-108 Q1)", async () => {
    const DOC: DocumentReaderView = {
      document_id: "doc-1",
      title: "Notes",
      text: "Amelia Burke travels to Birmingham.",
      truncated: false,
      spans: [],
      has_file: true,
    };
    const candidate = (id: string, entityType: string, name: string) => ({
      id,
      document_id: "doc-1",
      entity_type: entityType,
      properties: { name },
      confidence: 1,
      status: "pending",
    });
    serve({
      "/documents/doc-1/reader": { status: 200, body: DOC },
      "/documents/doc-1/extract": {
        status: 200,
        body: { document_id: "doc-1", text: DOC.text, candidates: [candidate("c1", "Person", "Amelia Burke"), candidate("c2", "Location", "Birmingham")] },
      },
      "/documents/doc-1/candidates/accept": {
        status: 200,
        body: {
          accepted: [{ node_id: "n1", delta: { seq: 2, op: "add", nodes: [], edges: [] } }],
          refusals: [{ candidate_id: "c2", words: "already decided; a finding is accepted or rejected once" }],
        },
      },
    });
    const onDelta = vi.fn();
    render(
      <DocumentReader
        apiBaseUrl="http://api.test"
        bearerToken="tok"
        investigationId="inv-1"
        documentId="doc-1"
        ontology={ONTOLOGY}
        labelOf={(id) => id}
        onClose={vi.fn()}
        onDelta={onDelta}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Quick scan" }));
    fireEvent.click(await screen.findByRole("button", { name: "Accept all pending (2)" }));
    const status = await screen.findByText(/1 accepted; 1 refused/);
    expect(status.textContent).toContain("already decided");
    expect(onDelta).toHaveBeenCalledTimes(1);
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
    fireEvent.click(await screen.findByRole("button", { name: "Quick scan" }));
    fireEvent.click(await screen.findByRole("button", { name: /Reject Endpoint · Houston/ }));
    expect(await screen.findByText("Rejected")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Accept Endpoint · Houston/ })).toBeNull();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/candidates/c1/reject"))).toBe(true);
    // Only the extraction's own delta (the email's Document); a rejection draws nothing.
    expect(onDelta).toHaveBeenCalledTimes(1);
  });

  // ADR-098 Amendment 1 (owner, 9 October 2026): the two extraction actions are equal, always
  // offered, each saying what it does — and a pending finding is shown where it sits in the text.
  it("offers Quick scan and Deep read (model) as equal buttons, each saying what it does", async () => {
    serve({ "/documents/email%3Aev-1/reader": { status: 200, body: EMAIL } });
    mount();
    const dialog = await screen.findByRole("dialog", { name: "Reading: Dabhol" });
    expect(await screen.findByRole("button", { name: "Quick scan" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Deep read (model)" })).toBeTruthy();
    expect(dialog.textContent).toContain("Names, emails and numbers, in seconds");
    expect(dialog.textContent).toContain("A slower, deeper read; findings are added");
  });

  it("keeps both extraction buttons offered after findings are listed", async () => {
    serve({
      "/documents/email%3Aev-1/reader": { status: 200, body: EMAIL },
      "/links/e1/events/ev-1/extract": {
        status: 200,
        body: { document_id: "email:ev-1", delta: { seq: 2, op: "add", nodes: [], edges: [] }, candidates: [] },
      },
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Quick scan" }));
    await screen.findByText("No entities were found in this document.");
    expect(screen.getByRole("button", { name: "Quick scan" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Deep read (model)" })).toBeTruthy();
  });

  it("shows a pending finding where it sits in the text, not yet accepted", async () => {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode("plant"));
    const plantHash = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
    serve({
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
              entity_type: "Organisation",
              properties: { name: "plant" },
              confidence: 0.9,
              status: "pending",
              locator: "char span 28-33",
              excerpt_hash: plantHash,
            },
          ],
        },
      },
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Quick scan" }));
    const marked = await screen.findByTitle("Organisation — found, not yet accepted");
    expect(marked.textContent).toBe("plant");
  });

  it("shows a legend naming each highlighted type in its colour, dashed meaning not yet accepted", async () => {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode("plant"));
    const plantHash = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
    serve({
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
              entity_type: "Organisation",
              properties: { name: "plant" },
              confidence: 0.9,
              status: "pending",
              locator: "char span 28-33",
              excerpt_hash: plantHash,
            },
          ],
        },
      },
    });
    mount();
    // The accepted Person span alone already earns a legend.
    const legend = await screen.findByLabelText("Highlight colours");
    expect(legend.textContent).toContain("Person");
    // A pending finding adds its type, and the dashed meaning is said.
    fireEvent.click(screen.getByRole("button", { name: "Quick scan" }));
    await waitFor(() => expect(legend.textContent).toContain("Organisation"));
    expect(legend.textContent).toContain("dashed: found, not yet accepted");
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
    expect(screen.queryByRole("button", { name: "Quick scan" })).toBeNull();
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
    fireEvent.click(await screen.findByRole("button", { name: "Quick scan" }));
    fireEvent.click(await screen.findByRole("button", { name: /Accept Person · WOLSKI/ }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/documents/content%3A1/candidates/c1/accept"))).toBe(true),
    );
  });
});

// ADR-098 decision 5: the analyst marks words in the text as an entity.
describe("DocumentReader: marking an entity", () => {
  it("marks typed words as the chosen type, sending where they are in the text, and draws the result", async () => {
    const fetchMock = serve({
      "/documents/email%3Aev-1/reader": { status: 200, body: EMAIL },
      "/documents/email%3Aev-1/designations": {
        status: 200,
        body: { node_id: "o1", delta: { seq: 5, op: "add", nodes: [], edges: [] } },
      },
    });
    const { onDelta } = mount();
    const words = await screen.findByRole("textbox", { name: "Words to mark" });
    fireEvent.change(words, { target: { value: "the plant" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Mark as" }), { target: { value: "Location" } });
    fireEvent.click(screen.getByRole("button", { name: "Mark" }));
    expect(await screen.findByText("Marked “the plant” as a Location.")).toBeTruthy();
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/designations"))!;
    expect(JSON.parse(String(((call as unknown[])[1] as RequestInit).body))).toEqual({
      entity_type: "Location",
      text: "the plant",
      start: 24,
      end: 33,
    });
    expect(onDelta).toHaveBeenCalledWith({ seq: 5, op: "add", nodes: [], edges: [] });
  });

  it("says when the words are not in the text, and sends nothing", async () => {
    const fetchMock = serve({ "/documents/email%3Aev-1/reader": { status: 200, body: EMAIL } });
    mount();
    fireEvent.change(await screen.findByRole("textbox", { name: "Words to mark" }), { target: { value: "Ken Lay" } });
    fireEvent.click(screen.getByRole("button", { name: "Mark" }));
    expect(await screen.findByText("Those words are not in this document.")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/designations"))).toBe(false);
  });
});

// ADR-098 decisions 2 and 3: the fast recogniser first, the language model on request.
describe("DocumentReader: Stanza first, the model on request", () => {
  const finding = (id: string, model: string, confidence: number) => ({
    id,
    document_id: "email:ev-1",
    entity_type: "Person",
    properties: { family_name: id === "s1" ? "MERCER" : "PLANT" },
    confidence,
    model,
    status: "pending",
  });

  it("Quick scan asks the recogniser and says each finding is Stanza's", async () => {
    const fetchMock = serve({
      "/documents/email%3Aev-1/reader": { status: 200, body: EMAIL },
      "/links/e1/events/ev-1/extract": {
        status: 200,
        body: { document_id: "email:ev-1", delta: { seq: 2, op: "add", nodes: [], edges: [] }, candidates: [finding("s1", "stanza:1.10.1", 1)] },
      },
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Quick scan" }));
    expect(await screen.findByText(/found by Stanza/)).toBeTruthy();
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/extract"))!;
    expect(JSON.parse(String(((call as unknown[])[1] as RequestInit).body))).toEqual({ using: "recogniser" });
  });

  it("Deep read (model) asks the model, after a fast pass too, and adds its findings", async () => {
    let calls = 0;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/reader")) return { ok: true, status: 200, json: async () => EMAIL };
      if (url.endsWith("/extract")) {
        calls += 1;
        const using = JSON.parse(String(init?.body)).using;
        const candidates = using === "model" ? [finding("m1", "qwen2.5:7b-instruct", 0.9)] : [finding("s1", "stanza:1.10.1", 1)];
        return { ok: true, status: 200, json: async () => ({ document_id: "email:ev-1", delta: { seq: 2, op: "add", nodes: [], edges: [] }, candidates }) };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetchMock);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Quick scan" }));
    await screen.findByText(/found by Stanza/);
    fireEvent.click(screen.getByRole("button", { name: "Deep read (model)" }));
    expect(await screen.findByText(/90%/)).toBeTruthy();
    expect(screen.getByText(/found by Stanza/)).toBeTruthy(); // the fast pass's finding stays
    expect(calls).toBe(2);
    const bodies = fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/extract")).map(([, i]) => JSON.parse(String(i?.body)));
    expect(bodies).toEqual([{ using: "recogniser" }, { using: "model" }]);
  });
});
