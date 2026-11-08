// @vitest-environment jsdom
// Admin › Models (ADR-135 Amendment 2): the key field is write-only — never filled, cleared once
// sent, the key never on the page afterwards, even when the Conduit refuses — and each action
// reaches its route with the Conduit's words shown back.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Models } from "./Models";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const PLANTED = "sk-PLANTED-glass-key-Q7Z4";
const GEMINI = { name: "gemini", label: "Gemini", roles: { extraction: "gemini-2.5-flash" }, api_base: null, privacy_contract: false, contract_reference: null };
const VIEW = {
  engines: [{ provider: GEMINI, key_state: "none", key_set_at: null, key_set_by: null, default_for: [] }],
  defaults: {},
  local_models: { extraction: "qwen2.5:7b-instruct", vision: null, transcription: null, embedding: "all-minilm" },
  local_only: false,
  sendable_handling_codes: ["O"],
  source: "models file",
};
const SET = { ...VIEW, engines: [{ ...VIEW.engines[0], key_state: "set", key_set_at: "2026-11-08T10:00:00Z", key_set_by: "admin-1" }] };

const NO_FIGURES = { calls: 0, succeeded: 0, failed: 0, prompt_tokens: 0, completion_tokens: 0, tokens: 0 };
const NO_USAGE = { start: "2026-11-01", end: "2026-11-08", rows: [], by_engine: {}, by_job: {}, total: NO_FIGURES };

type Answer = { status: number; body: unknown };

function stub(answers: (path: string, init?: RequestInit) => Answer | undefined) {
  const sent: { path: string; method: string; body: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(String(url)).pathname;
      sent.push({ path, method: init?.method ?? "GET", body: String(init?.body ?? "") });
      const answer = answers(path, init) ??
        (path === "/v1/admin/models/history"
          ? { status: 200, body: { entries: [] } }
          : path === "/v1/admin/models/usage"
            ? { status: 200, body: NO_USAGE }
            : { status: 200, body: VIEW });
      return { ok: answer.status < 400, status: answer.status, json: async () => answer.body } as Response;
    }),
  );
  return sent;
}

describe("Models", () => {
  it("sends the key once, clears the field, and never shows it again", async () => {
    const sent = stub((path, init) =>
      path === "/v1/admin/models/engines/gemini/key" && init?.method === "PUT" ? { status: 200, body: SET } : undefined,
    );
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Enter key for Gemini" }));
    const field = screen.getByLabelText(/Key for Gemini/) as HTMLInputElement;
    expect(field.type).toBe("password");
    expect(field.getAttribute("autocomplete")).toBe("off");
    expect(field.value).toBe("");
    fireEvent.change(field, { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Set the key" }));
    await screen.findByText(/the key is set/);
    const puts = sent.filter((s) => s.method === "PUT");
    expect(puts).toEqual([{ path: "/v1/admin/models/engines/gemini/key", method: "PUT", body: JSON.stringify({ key: PLANTED }) }]);
    expect(document.body.innerHTML).not.toContain(PLANTED);
    expect(document.body.innerHTML).not.toContain("Q7Z4");
    expect(screen.getByText("Key set")).toBeTruthy();
  });

  it("shows the Conduit's refusal in its words and still never the key", async () => {
    stub((path, init) =>
      path === "/v1/admin/models/engines/gemini/key" && init?.method === "PUT"
        ? { status: 502, body: { detail: { error: "model_admin_refused", detail: "The model gateway refused the key (HTTP 500). Run ospreyflow doctor." } } }
        : undefined,
    );
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Enter key for Gemini" }));
    fireEvent.change(screen.getByLabelText(/Key for Gemini/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Set the key" }));
    expect((await screen.findByRole("alert")).textContent).toContain("The model gateway refused the key");
    expect(document.body.innerHTML).not.toContain(PLANTED);
  });

  it("tests the connection and says what the gateway answered, in fixed words", async () => {
    const sent = stub((path) =>
      path === "/v1/admin/models/engines/gemini/test"
        ? { status: 200, body: { engine: "gemini", outcome: "cooling_down", ok: false, words: "Not a lasting failure: try again in a minute." } }
        : path === "/v1/admin/models" ? { status: 200, body: SET } : undefined,
    );
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Test the connection to Gemini" }));
    expect((await screen.findByRole("status")).textContent).toContain("try again in a minute");
    expect(sent.some((s) => s.path.endsWith("/test") && s.method === "POST")).toBe(true);
  });

  it("adds an engine with its models and contract, and saves each job's default", async () => {
    const sent = stub(() => undefined);
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add an engine" }));
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "openai" } });
    fireEvent.change(screen.getByLabelText(/Extraction and Ask: the provider/), { target: { value: "gpt-4o-mini" } });
    fireEvent.click(screen.getByLabelText(/Under a privacy contract/));
    fireEvent.change(screen.getByLabelText(/reference/), { target: { value: "DPA 2026/07" } });
    fireEvent.click(screen.getByRole("button", { name: "Add the engine" }));
    await waitFor(() => expect(sent.some((s) => s.method === "POST" && s.path === "/v1/admin/models/engines")).toBe(true));
    const added = JSON.parse(sent.find((s) => s.method === "POST")!.body);
    expect(added.provider).toMatchObject({ name: "openai", roles: { extraction: "gpt-4o-mini" }, privacy_contract: true, contract_reference: "DPA 2026/07" });
    fireEvent.change(await screen.findByLabelText("Extraction and Ask"), { target: { value: "gemini" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the defaults" }));
    await waitFor(() => expect(sent.some((s) => s.path === "/v1/admin/models/defaults")).toBe(true));
    expect(JSON.parse(sent.find((s) => s.path === "/v1/admin/models/defaults")!.body)).toEqual({ defaults: { extraction: "gemini" } });
  });

  it("offers no engine to add on a local-only deployment, and says why", async () => {
    stub((path) => (path === "/v1/admin/models" ? { status: 200, body: { ...VIEW, engines: [], local_only: true } } : undefined));
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    expect(await screen.findByText(/This deployment is local only/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add an engine" })).toBeNull();
  });
});
