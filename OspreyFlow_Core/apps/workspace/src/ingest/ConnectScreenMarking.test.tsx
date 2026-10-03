// @vitest-environment jsdom
//
// Connect's classification is optional and a blank one is recorded as PUBLIC (ADR-068; owner
// rulings of 3 October 2026), and the connectors with nothing behind them are greyed *with a reason*
// ("Keep them, but say why"). The server makes the blank true; these prove the screen says it and
// does not stop the analyst saving.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConnectScreen } from "./ConnectScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const CATALOGUE = [
  { id: "generic-csv", label: "CSV file", group: "Generic", structured: true, available: true },
  { id: "pdf", label: "PDF document", group: "Documents", structured: false, available: false },
];

function stub(classification: string[] = ["PUBLIC", "OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"], catalogue = CATALOGUE) {
  const posts: { url: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const path = url.replace("http://api", "");
      let body: unknown;
      let status = 200;
      if (path === "/v1/ingest/connectors") body = catalogue;
      else if (path === "/v1/handling-scheme") {
        body = {
          name: "uk-le",
          classification,
          handling_codes: { P: { label: "Permissive", dissemination: "permitted" } },
        };
      } else if (path === "/v1/ingest/recipes" && method === "GET") body = [];
      else if (path === "/v1/ingest/source-files") body = { root: "/r", files: [] };
      else if (path === "/v1/ingest/recipes" && method === "POST") {
        const sent = JSON.parse(String(init?.body)) as Record<string, unknown>;
        posts.push({ url: path, body: sent });
        status = 201;
        body = {
          recipe_id: "r1", version: 1, status: "draft", label: sent.label, connector_profile: sent.connector_profile,
          source_location: null, handling: { classification: "PUBLIC" }, legal_basis: null, owning_unit: "u",
          created_by: "a", created_at: "2026-10-03T00:00:00Z", ready_for_profile: false,
        };
      } else throw new Error(`unexpected request ${method} ${path}`);
      return { ok: status < 300, status, json: async () => body };
    }),
  );
  return { posts };
}

async function open() {
  render(<ConnectScreen apiBaseUrl="http://api" bearerToken="tok" />);
  await screen.findByRole("button", { name: "Choose file…" });
}

const classificationBox = () =>
  screen.getByRole("combobox", { name: "Classification" }) as HTMLSelectElement;

describe("Connect: classification is optional and blank means PUBLIC", () => {
  it("lists PUBLIC among the classifications the scheme offers", async () => {
    stub();
    await open();
    const options = Array.from(classificationBox().options).map((o) => o.value);
    expect(options).toContain("PUBLIC");
  });

  it("starts blank, and the blank choice can be chosen again (it is not a disabled placeholder)", async () => {
    stub();
    await open();
    const box = classificationBox();
    expect(box.value).toBe("");
    const blank = Array.from(box.options).find((o) => o.value === "")!;
    expect(blank.disabled).toBe(false);
    fireEvent.change(box, { target: { value: "SECRET" } });
    fireEvent.change(box, { target: { value: "" } });
    expect(box.value).toBe("");
  });

  it("says beside the box what a blank classification becomes, and stops saying it once one is chosen", async () => {
    stub();
    await open();
    expect(screen.getByText("Left blank: recorded as PUBLIC")).toBeTruthy();
    fireEvent.change(classificationBox(), { target: { value: "OFFICIAL" } });
    expect(screen.queryByText("Left blank: recorded as PUBLIC")).toBeNull();
    fireEvent.change(classificationBox(), { target: { value: "" } });
    expect(screen.getByText("Left blank: recorded as PUBLIC")).toBeTruthy();
  });

  it("names the scheme's lowest level when the scheme has no PUBLIC", async () => {
    stub(["UNCLASSIFIED", "RESTRICTED"]);
    await open();
    expect(screen.getByText("Left blank: recorded as UNCLASSIFIED")).toBeTruthy();
  });

  it("lets a draft be saved with no classification, and sends none (the server records PUBLIC)", async () => {
    const { posts } = stub();
    await open();
    fireEvent.change(screen.getByPlaceholderText("Carrier A — call detail records"), {
      target: { value: "Carrier A" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Connector" }), {
      target: { value: "generic-csv" },
    });
    const create = screen.getByRole("button", { name: "Create draft" }) as HTMLButtonElement;
    expect(create.disabled).toBe(false);
    fireEvent.click(create);
    await waitFor(() => expect(posts).toHaveLength(1));
    expect((posts[0]!.body.handling as Record<string, string>).classification).toBeUndefined();
  });
});

describe("Connect: connectors with nothing behind them say why they are greyed", () => {
  it("explains the greyed formats under the connector box", async () => {
    stub();
    await open();
    expect(screen.getByText("Greyed formats have no connector built yet.")).toBeTruthy();
  });

  it("still shows each greyed format, disabled, labelled not yet available", async () => {
    stub();
    await open();
    const pdf = screen.getByRole("option", { name: /PDF document/ }) as HTMLOptionElement;
    expect(pdf.disabled).toBe(true);
    expect(pdf.textContent).toContain("not yet available");
  });

  it("does not show the explanation when every connector is available", async () => {
    stub(undefined, [CATALOGUE[0]!]);
    await open();
    expect(screen.queryByText("Greyed formats have no connector built yet.")).toBeNull();
  });
});
