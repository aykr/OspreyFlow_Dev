// @vitest-environment jsdom
//
// The Connect stage's file picker (ADR-067, which amends ruling R6): the analyst chooses a file on
// their own computer and it is uploaded to the deployment's ingest folder, then offered and
// selected, instead of being asked to type a path the server could never open.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConnectScreen } from "./ConnectScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

interface Reply {
  status: number;
  body: unknown;
}

const CATALOGUE = [
  { id: "generic-csv", label: "CSV file", group: "Generic", structured: true, available: true },
  { id: "pdf", label: "PDF document", group: "Documents", structured: false, available: false },
];
const SCHEME = {
  name: "uk-le",
  classification: ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"],
  handling_codes: { P: { label: "Permissive", dissemination: "permitted" } },
};
const UPLOADED = {
  name: "carrier.csv",
  source_location: "/var/lib/osprey/ingest/uploaded/carrier.csv",
  size_bytes: 8,
  modified_at: 1,
  uploaded: true,
};

function stub(upload: () => Reply) {
  let uploaded = false;
  const calls: { method: string; url: string; init?: RequestInit }[] = [];
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = url.replace("http://api", "");
    calls.push({ method, url: path, init });
    let reply: Reply;
    if (path === "/v1/ingest/connectors") reply = { status: 200, body: CATALOGUE };
    else if (path === "/v1/handling-scheme") reply = { status: 200, body: SCHEME };
    else if (path === "/v1/ingest/recipes") reply = { status: 200, body: [] };
    else if (path === "/v1/ingest/source-files" && method === "GET") {
      reply = {
        status: 200,
        body: { root: "/var/lib/osprey/ingest", files: uploaded ? [UPLOADED] : [] },
      };
    } else if (path.startsWith("/v1/ingest/source-files?name=") && method === "POST") {
      reply = upload();
      if (reply.status === 201) uploaded = true;
    } else throw new Error(`unexpected request ${method} ${path}`);
    return {
      ok: reply.status < 300,
      status: reply.status,
      json: async () => reply.body,
    };
  });
  vi.stubGlobal("fetch", mock);
  return { calls };
}

async function open() {
  render(<ConnectScreen apiBaseUrl="http://api" bearerToken="tok" />);
  await screen.findByRole("button", { name: "Choose file…" });
}

function pick(file: File) {
  const input = screen.getByLabelText("Choose a file from your computer") as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
}

describe("Connect: choose a file from your computer", () => {
  it("offers a Choose file button even when the ingest folder is empty", async () => {
    stub(() => ({ status: 201, body: UPLOADED }));
    await open();
    expect(screen.getByRole("button", { name: "Choose file…" })).toBeTruthy();
  });

  it("the button opens the system file picker (it presses the hidden file input), so the keyboard reaches it", async () => {
    stub(() => ({ status: 201, body: UPLOADED }));
    await open();
    const input = screen.getByLabelText("Choose a file from your computer") as HTMLInputElement;
    const clicked = vi.fn();
    input.addEventListener("click", clicked);
    const button = screen.getByRole("button", { name: "Choose file…" });
    button.focus();
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    expect(clicked).toHaveBeenCalledTimes(1);
  });

  it("only lets the system picker offer the types the server accepts", async () => {
    stub(() => ({ status: 201, body: UPLOADED }));
    await open();
    const input = screen.getByLabelText("Choose a file from your computer") as HTMLInputElement;
    expect(input.accept).toContain(".csv");
    expect(input.accept).not.toContain(".exe");
  });

  it("sends the chosen file's name and bytes to the server with the bearer token", async () => {
    const { calls } = stub(() => ({ status: 201, body: UPLOADED }));
    await open();
    pick(new File(["a,b\n1,2\n"], "carrier.csv", { type: "text/csv" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe("/v1/ingest/source-files?name=carrier.csv");
    expect((post.init?.headers as Record<string, string>).Authorization).toBe("Bearer tok");
    expect(post.init?.body).toBeInstanceOf(File);
  });

  it("encodes a name with spaces and symbols so it reaches the server whole", async () => {
    const { calls } = stub(() => ({ status: 201, body: UPLOADED }));
    await open();
    pick(new File(["x"], "Q3 calls & texts.csv"));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.url).toBe(
      "/v1/ingest/source-files?name=Q3%20calls%20%26%20texts.csv",
    );
  });

  it("selects the uploaded file as the data and refreshes the folder list", async () => {
    stub(() => ({ status: 201, body: UPLOADED }));
    await open();
    pick(new File(["a,b\n1,2\n"], "carrier.csv"));
    await waitFor(() =>
      expect(
        screen.getByText((_, el) => el?.tagName === "P" && el.textContent === "Selected: carrier.csv"),
      ).toBeTruthy(),
    );
    const typed = screen.getByLabelText("Where is the data?") as HTMLInputElement;
    expect(typed.value).toBe(UPLOADED.source_location);
    // The folder now lists it too.
    const list = await screen.findByLabelText("Choose a file from the ingest folder");
    expect(within(list).getByText(/carrier\.csv/)).toBeTruthy();
  });

  it("says what the server said when it refuses, and changes nothing", async () => {
    stub(() => ({ status: 409, body: { detail: "A file with that name is already in the ingest folder." } }));
    await open();
    pick(new File(["a"], "carrier.csv"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("A file with that name is already in the ingest folder.");
    expect((screen.getByLabelText("Where is the data?") as HTMLInputElement).value).toBe("");
  });

  it("says plainly when it cannot reach the server for the upload", async () => {
    stub(() => {
      throw new Error("network down");
    });
    await open();
    pick(new File(["a"], "carrier.csv"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("network down");
  });

  it("shows that it is uploading and does not let a second upload start meanwhile", async () => {
    let release: (r: Reply) => void = () => undefined;
    const held = new Promise<Reply>((resolve) => {
      release = resolve;
    });
    const { calls } = stub(() => ({ status: 201, body: UPLOADED }));
    const inner = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).getMockImplementation() as (url: string, init?: RequestInit) => Promise<unknown>;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if ((init?.method ?? "GET") === "POST" && url.includes("source-files")) {
          const reply = await held;
          calls.push({ method: "POST", url: url.replace("http://api", ""), init });
          return { ok: reply.status < 300, status: reply.status, json: async () => reply.body };
        }
        return inner(url, init);
      }),
    );
    await open();
    pick(new File(["a"], "carrier.csv"));
    const busy = await screen.findByRole("button", { name: "Uploading…" });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    release({ status: 201, body: UPLOADED });
    await screen.findByRole("button", { name: "Choose file…" });
  });

  it("keeps typing a path or address available, behind a plain disclosure", async () => {
    stub(() => ({ status: 201, body: UPLOADED }));
    await open();
    const disclosure = screen.getByText("Or type a path or address");
    expect(disclosure.closest("details")).toBeTruthy();
    expect(screen.getByLabelText("Where is the data?")).toBeTruthy();
  });
});
