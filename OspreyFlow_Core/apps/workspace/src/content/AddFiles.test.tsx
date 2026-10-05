// @vitest-environment jsdom
// ADR-094 step 3: files added straight to a case, standing alone or held by a node. Each needs a
// handling marking and a legal basis, like every source (spec 09 §2); each becomes a Document on the
// canvas; a refused file is said by name, and the rest still go.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AddFiles } from "./AddFiles";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function serve(answers: Record<string, { status: number; body: unknown }>) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    void init;
    if (String(url).endsWith("/v1/handling-scheme")) {
      return { ok: true, status: 200, json: async () => ({ classification: ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"] }) };
    }
    const name = new URL(String(url)).searchParams.get("name") ?? "";
    const answer = answers[name] ?? { status: 500, body: {} };
    return { ok: answer.status < 400, status: answer.status, json: async () => answer.body };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function mount(onDelta = vi.fn(), holder?: { id: string; label: string }) {
  render(
    <AddFiles
      apiBaseUrl="http://api"
      bearerToken="t"
      investigationId="inv-1"
      holder={holder}
      onDelta={onDelta}
      onClose={vi.fn()}
    />,
  );
  return onDelta;
}

function choose(...files: File[]) {
  fireEvent.change(screen.getByLabelText("Files"), { target: { files } });
}

describe("AddFiles", () => {
  it("uploads each file with its marking, legal basis and holder, and draws the Documents", async () => {
    const fetchMock = serve({
      "IMG_0042.jpg": { status: 200, body: { document_id: "content:1", delta: { seq: 2, op: "add", nodes: [], edges: [] } } },
    });
    const onDelta = mount(vi.fn(), { id: "phone-1", label: "07911123456" });
    expect(await screen.findByText(/held by 07911123456/)).toBeTruthy();
    choose(new File(["jpeg"], "IMG_0042.jpg", { type: "image/jpeg" }));
    fireEvent.change(await screen.findByLabelText("Marking"), { target: { value: "OFFICIAL-SENSITIVE" } });
    fireEvent.change(screen.getByLabelText("Legal basis"), { target: { value: "PACE s19 seizure" } });
    fireEvent.click(screen.getByRole("button", { name: "Add 1 file" }));
    await waitFor(() => expect(onDelta).toHaveBeenCalledTimes(1));
    const call = fetchMock.mock.calls.find(([u]) => String(u).includes("/documents?"));
    const url = new URL(String(call?.[0]));
    expect(url.pathname).toBe("/v1/investigations/inv-1/documents");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      name: "IMG_0042.jpg",
      classification: "OFFICIAL-SENSITIVE",
      legal_basis: "PACE s19 seizure",
      holder: "phone-1",
    });
    expect((call?.[1] as RequestInit).method).toBe("POST");
    expect(await screen.findByRole("status")).toHaveProperty("textContent", "1 file added.");
  });

  it("will not upload without a legal basis", async () => {
    serve({});
    mount();
    choose(new File(["x"], "note.txt", { type: "text/plain" }));
    expect((screen.getByRole("button", { name: "Add 1 file" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("names a refused file and still adds the rest", async () => {
    serve({
      "tool.exe": { status: 422, body: { error: "upload_refused", detail: "'tool.exe' is not a kind of file the reader can show" } },
      "note.txt": { status: 200, body: { document_id: "content:2", delta: { seq: 3, op: "add", nodes: [], edges: [] } } },
    });
    const onDelta = mount();
    choose(new File(["x"], "tool.exe"), new File(["y"], "note.txt", { type: "text/plain" }));
    fireEvent.change(screen.getByLabelText("Legal basis"), { target: { value: "Consent" } });
    fireEvent.click(screen.getByRole("button", { name: "Add 2 files" }));
    await waitFor(() => expect(onDelta).toHaveBeenCalledTimes(1));
    expect((await screen.findByRole("alert")).textContent).toContain("tool.exe");
    expect(screen.getByRole("status").textContent).toBe("1 file added.");
  });
});
