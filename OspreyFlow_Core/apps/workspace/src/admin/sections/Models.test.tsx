// @vitest-environment jsdom
// Admin › Models (ADR-135 Amendment 2): the key field is write-only — never filled, cleared once
// sent, the key never on the page afterwards, even when the Conduit refuses — and each action
// reaches its route with the Conduit's words shown back.
import { randomBytes } from "node:crypto";

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Models } from "./Models";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// The owner's rules for keys: a synthetic key, made at run time, in every test and plant. Its last
// characters stand for "any part of it" in the places a whole key might not be written.
const PLANTED = `sk-${randomBytes(16).toString("hex")}`;
const PART = PLANTED.slice(-8);
const GEMINI = { name: "gemini", label: "Gemini", roles: { extraction: "gemini-2.5-flash" }, api_base: null, privacy_contract: false, contract_reference: null };
const VIEW = {
  engines: [{ provider: GEMINI, key_state: "none", key_set_at: null, key_set_by: null, default_for: [] }],
  defaults: {},
  local_models: { extraction: "qwen2.5:7b-instruct", vision: null, transcription: null, embedding: "all-minilm" },
  local_only: false,
  sendable_handling_codes: ["O"],
  source: "models file",
  // What the Conduit sends off the cloud platform since Amendment 14: your own gateway on every profile.
  engine_kinds: ["provider", "gateway"],
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
  it("heads its parts with h2s beneath Admin's h1, sized as People's (ADR-145 Amendment 16)", async () => {
    stub(() => undefined);
    const { container } = render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    await screen.findByRole("heading", { name: "Engines" });
    const headings = [...container.querySelectorAll("h1, h2, h3, h4, h5, h6")];
    expect(headings.map((h) => h.tagName)).toEqual(headings.map(() => "H2"));
    expect(headings.length).toBeGreaterThan(2);
    expect(headings.every((h) => h.classList.contains("value"))).toBe(true);
  });

  it("marks an engine the render did not make, in the Conduit's words (ADR-135 Amendment 8)", async () => {
    const words = "not made by the render: Declare it in osprey.yaml, re-render, and have the platform team apply the Terraform";
    const UNMADE = { ...VIEW, engines: [{ ...VIEW.engines[0], not_made: words }] };
    stub((path) => (path === "/v1/admin/models" ? { status: 200, body: UNMADE } : undefined));
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    expect((await screen.findByRole("note")).textContent).toBe(words);
  });

  it("sends the key once, clears the field, and never shows it again", async () => {
    const sent = stub((path, init) =>
      path === "/v1/admin/models/engines/gemini/key" && init?.method === "PUT" ? { status: 200, body: SET } : undefined,
    );
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Enter key for Gemini" }));
    const field = screen.getByLabelText(/Key for Gemini/) as HTMLInputElement;
    expect(field.type).toBe("password");
    expect(field.getAttribute("autocomplete")).toBe("new-password");
    expect(field.value).toBe("");
    fireEvent.change(field, { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Set the key" }));
    await screen.findByText(/the key is set/);
    const puts = sent.filter((s) => s.method === "PUT");
    expect(puts).toEqual([{ path: "/v1/admin/models/engines/gemini/key", method: "PUT", body: JSON.stringify({ key: PLANTED }) }]);
    expect(document.body.innerHTML).not.toContain(PLANTED);
    expect(document.body.innerHTML).not.toContain(PART);
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

  // ADR-135 Amendment 14 (the owner's first slice): the providers this profile offers, as the Conduit lists them.
  const GEMINI_ENTRY = { id: "gemini", label: "Google Gemini", kind: "provider", address: "https://generativelanguage.googleapis.com", address_asked: false, key: true, example: "gemini-3.8-flash", jobs: ["extraction", "vision", "transcription"], prefix: "gemini", note: "" };
  const ANTHROPIC_ENTRY = { id: "anthropic", label: "Anthropic", kind: "provider", address: "https://api.anthropic.com", address_asked: false, key: true, example: "claude-sonnet-5-5", jobs: ["extraction", "vision"], prefix: "anthropic", note: "" };
  const AZURE_ENTRY = { id: "azure", label: "Azure OpenAI", kind: "provider", address: null, address_asked: true, key: true, example: null, jobs: ["extraction", "vision", "transcription"], prefix: "azure", note: "Give your Azure OpenAI resource's address, and each deployment's name." };
  const GATEWAY_ENTRY = { id: "gateway", label: "Another provider or your own gateway", kind: "gateway", address: null, address_asked: true, key: true, example: null, jobs: ["extraction", "vision", "transcription"], prefix: "openai", note: "Give its address (https://…). Its models are named, and each is checked by one call." };
  const BEDROCK_ENTRY = { id: "bedrock", label: "Amazon Bedrock", kind: "bedrock", address: null, address_asked: false, key: false, example: "amazon.nova-pro-v1:0", jobs: ["extraction", "vision"], prefix: "bedrock", note: "Amazon Bedrock is reached by this deployment's own role, in London only: no key and no address." };
  const LISTED = { ...VIEW, engines: [], engine_kinds: ["provider", "gateway"], providers: [GEMINI_ENTRY, ANTHROPIC_ENTRY, AZURE_ENTRY, GATEWAY_ENTRY], checks: [] };
  const CLOUD_LISTED = { ...LISTED, engine_kinds: ["provider", "gateway", "bedrock"], providers: [GEMINI_ENTRY, ANTHROPIC_ENTRY, AZURE_ENTRY, BEDROCK_ENTRY, GATEWAY_ENTRY] };
  const PASSED = { engine: "gemini", ok: true, check: "chk-1", models: [{ roles: ["extraction"], outcome: "ok", ok: true, words: "Extraction and Ask: Connected: the engine answered." }], words: "The key and every model answered. Add the engine within 15 minutes to offer it to analysts." };
  const ADDED = { ...LISTED, engines: [{ provider: { ...GEMINI, label: "Google Gemini", roles: { extraction: "gemini-3.8-flash" } }, key_state: "set", key_set_at: "2026-11-15T12:00:00Z", key_set_by: "admin-1", default_for: [] }] };
  const listed = (view: unknown) => (path: string, init?: RequestInit) =>
    path === "/v1/admin/models" && (init?.method ?? "GET") === "GET" ? { status: 200, body: view } : undefined;
  const openAdd = async () => {
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add an engine" }));
  };
  const options = () => Array.from((screen.getByLabelText("Provider") as HTMLSelectElement).options).map((o) => o.textContent);

  it("lists the providers this deployment offers, fills the label and shows the provider's own address", async () => {
    stub(listed(LISTED));
    await openAdd();
    expect(options()).toEqual(["Google Gemini", "Anthropic", "Azure OpenAI", "Another provider or your own gateway"]);
    expect((screen.getByLabelText("Label analysts see") as HTMLInputElement).value).toBe("Google Gemini");
    expect(screen.getByText("Address: https://generativelanguage.googleapis.com")).toBeTruthy();
    expect(screen.queryByLabelText(/^Address/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Change the address of Google Gemini" }));
    expect(screen.getByLabelText(/Address of the gateway in front of it/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "anthropic" } });
    expect((screen.getByLabelText("Label analysts see") as HTMLInputElement).value).toBe("Anthropic");
  });

  it("offers only the provider's jobs, each a typed name beside a current example", async () => {
    stub(listed(LISTED));
    await openAdd();
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "anthropic" } });
    expect(screen.getByLabelText("Extraction and Ask: model name")).toBeTruthy();
    expect(screen.getByLabelText("Image description: model name")).toBeTruthy();
    expect(screen.queryByLabelText(/Transcription: model name/)).toBeNull();
    const field = screen.getByLabelText("Extraction and Ask: model name") as HTMLInputElement;
    expect(field.placeholder).toBe("such as claude-sonnet-5-5");
    expect(document.getElementById(field.getAttribute("aria-describedby")!)!.textContent).toMatch(/A job left empty uses this deployment's own model/);
  });

  it("asks Azure's and another provider's address, and says so", async () => {
    stub(listed(LISTED));
    await openAdd();
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "azure" } });
    expect(screen.getByLabelText("Address (https://)")).toBeTruthy();
    expect(screen.getByText(/Azure OpenAI resource's address/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "gateway" } });
    expect(screen.getByLabelText("Address (https://)")).toBeTruthy();
    expect(screen.getByLabelText(/^Token/)).toBeTruthy();
  });

  it("offers no Bedrock off the cloud platform, and on it Bedrock with neither key nor address, saying why", async () => {
    stub(listed(LISTED));
    await openAdd();
    expect(options()).not.toContain("Amazon Bedrock");
    cleanup();
    const sent = stub((path, init) =>
      path === "/v1/admin/models/checks" ? { status: 200, body: { ...PASSED, engine: "bedrock", models: [{ ...PASSED.models[0] }] } } : listed(CLOUD_LISTED)(path, init),
    );
    await openAdd();
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "bedrock" } });
    expect(screen.getByText(/own role, in London only: no key and no address/)).toBeTruthy();
    expect(screen.queryByLabelText(/^Key/)).toBeNull();
    expect(screen.queryByLabelText(/^Address/)).toBeNull();
    expect(screen.queryByText(/^Address:/)).toBeNull();
    fireEvent.change(screen.getByLabelText("Extraction and Ask: model name"), { target: { value: "amazon.nova-pro-v1:0" } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    await screen.findByRole("button", { name: "Add the engine" });
    const body = JSON.parse(sent.find((s) => s.path === "/v1/admin/models/checks")!.body);
    expect(body).toEqual({ provider: expect.objectContaining({ name: "bedrock", kind: "bedrock", auth: "iam_role", api_base: null }) });
  });

  it("previews what analysts will see, in their engine list's own words", async () => {
    stub(listed(LISTED));
    await openAdd();
    const preview = () => screen.getByText(/^Analysts will see:/).textContent;
    expect(preview()).toBe("Analysts will see: Google Gemini (no contract). It is offered only for cases whose data may leave this deployment.");
    fireEvent.change(screen.getByLabelText("Label analysts see"), { target: { value: "Gemini" } });
    fireEvent.click(screen.getByLabelText(/Under a privacy contract/));
    expect(preview()).toMatch(/^Analysts will see: Gemini \(under contract\)\./);
  });

  it("checks the key and the typed model before Add, adds from the check, and never sends the key again", async () => {
    const sent = stub((path, init) =>
      path === "/v1/admin/models/checks" ? { status: 200, body: PASSED }
        : path === "/v1/admin/models/checks/chk-1/add" ? { status: 200, body: ADDED }
          : listed(LISTED)(path, init),
    );
    await openAdd();
    expect(screen.queryByRole("button", { name: "Add the engine" })).toBeNull();
    // The prefix is the form's business: typed with it, sent without it.
    fireEvent.change(screen.getByLabelText("Extraction and Ask: model name"), { target: { value: "gemini/gemini-3.8-flash" } });
    const key = screen.getByLabelText(/^Key/) as HTMLInputElement;
    expect(key.type).toBe("password");
    expect(key.getAttribute("autocomplete")).toBe("new-password");
    expect(key.getAttribute("data-1p-ignore")).toBe("true");
    expect(key.value).toBe("");
    expect((screen.getByRole("button", { name: "Check" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(key, { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(key.value).toBe("");
    await screen.findByText(/Add the engine within 15 minutes/);
    const checks = sent.filter((s) => s.path === "/v1/admin/models/checks");
    expect(checks).toHaveLength(1);
    expect(JSON.parse(checks[0]!.body)).toEqual({
      provider: { name: "gemini", label: "Google Gemini", roles: { extraction: "gemini-3.8-flash" }, api_base: null, privacy_contract: false, contract_reference: null },
      key: PLANTED,
    });
    fireEvent.click(screen.getByRole("button", { name: "Add the engine" }));
    await screen.findByText(/Google Gemini is added and offered to analysts/);
    const add = sent.find((s) => s.path === "/v1/admin/models/checks/chk-1/add")!;
    expect(add.method).toBe("POST");
    expect(sent.filter((s) => s.body.includes(PLANTED))).toEqual([checks[0]]);
    expect(document.body.innerHTML).not.toContain(PLANTED);
    expect(sent.some((s) => s.path === "/v1/admin/models/engines")).toBe(false);
  });

  it("ties a refused key and a refused model to their fields, offers no Add, and keeps no key", async () => {
    const refused = {
      engine: "gemini", ok: false, check: null,
      models: [
        { roles: ["extraction"], outcome: "model_not_offered", ok: false, words: "Extraction and Ask: The provider does not offer that model." },
        { roles: ["vision"], outcome: "key_refused", ok: false, words: "Image description: The key was refused." },
      ],
      words: "The provider does not offer that model. Nothing was kept: correct it and check again.",
    };
    stub((path, init) => (path === "/v1/admin/models/checks" ? { status: 200, body: refused } : listed(LISTED)(path, init)));
    await openAdd();
    fireEvent.change(screen.getByLabelText("Extraction and Ask: model name"), { target: { value: "gemini-not-a-model" } });
    fireEvent.change(screen.getByLabelText("Image description: model name"), { target: { value: "gemini-3.8-flash" } });
    fireEvent.change(screen.getByLabelText(/^Key/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/Nothing was kept/);
    const model = screen.getByLabelText("Extraction and Ask: model name");
    expect(model.getAttribute("aria-invalid")).toBe("true");
    expect(model.getAttribute("aria-describedby")).toContain("add-engine-job-extraction-error");
    expect(document.getElementById("add-engine-job-extraction-error")!.textContent).toBe("Extraction and Ask: The provider does not offer that model.");
    const key = screen.getByLabelText(/^Key/) as HTMLInputElement;
    expect(key.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById("add-engine-key-error")!.textContent).toBe("Image description: The key was refused.");
    expect(key.value).toBe("");
    expect(screen.queryByRole("button", { name: "Add the engine" })).toBeNull();
    expect(document.body.innerHTML).not.toContain(PLANTED);
    // The owner's ruling 22: each answer by its job, in the Conduit's words; no model name is sent
    // back to be shown, so none is (the typed one stays in its own field alone).
    const said = [...document.querySelectorAll(".admin-models-result li")].map((li) => li.textContent);
    expect(said).toEqual(["Extraction and Ask: The provider does not offer that model.", "Image description: The key was refused."]);
  });

  it("ties the Conduit's refusal of a key-shaped label to the label", async () => {
    const words = "The label looks like a key. It is shown to analysts, so give it in words, and the key in the key field; nothing was checked.";
    stub((path, init) => (path === "/v1/admin/models/checks" ? { status: 422, body: { detail: { error: "model_admin_refused", detail: words } } } : listed(LISTED)(path, init)));
    await openAdd();
    fireEvent.change(screen.getByLabelText("Label analysts see"), { target: { value: PLANTED } });
    fireEvent.change(screen.getByLabelText(/^Key/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    await screen.findByRole("alert");
    const label = screen.getByLabelText("Label analysts see");
    expect(label.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(label.getAttribute("aria-describedby")!)!.textContent).toBe(words);
  });

  it("cancels a passed check, removing it", async () => {
    const sent = stub((path, init) =>
      path === "/v1/admin/models/checks" ? { status: 200, body: PASSED }
        : path === "/v1/admin/models/checks/chk-1" ? { status: 200, body: LISTED }
          : listed(LISTED)(path, init),
    );
    await openAdd();
    fireEvent.change(screen.getByLabelText("Extraction and Ask: model name"), { target: { value: "gemini-3.8-flash" } });
    fireEvent.change(screen.getByLabelText(/^Key/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    await screen.findByRole("button", { name: "Add the engine" });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await screen.findByText(/was not added; its check and key are removed/);
    expect(sent.find((s) => s.path === "/v1/admin/models/checks/chk-1")!.method).toBe("DELETE");
  });

  it("shows a check waiting for Add as being checked, never as an engine, and cancels it", async () => {
    const HELD = { ...LISTED, checks: [{ id: "chk-9", engine: "openai", label: "OpenAI", by: "admin-1", at: "2026-11-15T12:00:00Z", expires_at: "2026-11-15T12:15:00Z" }] };
    const sent = stub((path, init) => (path === "/v1/admin/models/checks/chk-9" ? { status: 200, body: LISTED } : listed(HELD)(path, init)));
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    const held = await screen.findByRole("table", { name: "Being checked" });
    expect(held.textContent).toMatch(/OpenAI.*not offered to analysts until it is added/);
    expect(screen.getByRole("table", { name: "Engines" }).textContent).not.toContain("OpenAI");
    fireEvent.click(screen.getByRole("button", { name: "Cancel the check of OpenAI" }));
    await screen.findByText(/OpenAI was not added/);
    expect(sent.find((s) => s.path === "/v1/admin/models/checks/chk-9")!.method).toBe("DELETE");
  });

  it("keeps the key in no browser storage, no address and no auto-completion (the key test's browser half)", async () => {
    localStorage.clear();
    sessionStorage.clear();
    const sent = stub((path, init) =>
      path === "/v1/admin/models/checks" ? { status: 200, body: PASSED }
        : path === "/v1/admin/models/checks/chk-1/add" ? { status: 200, body: ADDED }
          : listed(LISTED)(path, init),
    );
    const urls: string[] = [];
    const fetched = globalThis.fetch as unknown as { mock: { calls: [string][] } };
    await openAdd();
    const form = screen.getByRole("form", { name: "Add an engine" });
    expect(form.getAttribute("autocomplete")).toBe("off");
    fireEvent.change(screen.getByLabelText("Extraction and Ask: model name"), { target: { value: "gemini-3.8-flash" } });
    fireEvent.change(screen.getByLabelText(/^Key/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    fireEvent.click(await screen.findByRole("button", { name: "Add the engine" }));
    await screen.findByText(/is added and offered to analysts/);
    urls.push(...fetched.mock.calls.map(([url]) => String(url)), location.href);
    const stored = [localStorage, sessionStorage].flatMap((store) =>
      Array.from({ length: store.length }, (_, i) => `${store.key(i)}=${store.getItem(store.key(i)!)}`),
    );
    for (const place of [...urls, ...stored, document.cookie, document.body.innerHTML]) {
      expect(place).not.toContain(PLANTED);
      expect(place).not.toContain(PART);
    }
    // It did leave, once, in the check's body: the test cannot pass by sending nothing.
    expect(sent.filter((s) => s.body.includes(PLANTED)).map((s) => s.path)).toEqual(["/v1/admin/models/checks"]);
  });

  it("empties a typed key when the provider is changed, so it is never sent where it was not typed for", async () => {
    const sent = stub((path, init) => (path === "/v1/admin/models/checks" ? { status: 200, body: PASSED } : listed(LISTED)(path, init)));
    await openAdd();
    fireEvent.change(screen.getByLabelText(/^Key/), { target: { value: PLANTED } });
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "gateway" } });
    expect((screen.getByLabelText(/^Token/) as HTMLInputElement).value).toBe("");
    expect((screen.getByRole("button", { name: "Check" }) as HTMLButtonElement).disabled).toBe(true);
    expect(sent.some((s) => s.body.includes(PLANTED))).toBe(false);
  });

  it("ties each field the Conduit's rules refused to that field, in the Conduit's words", async () => {
    // The real Conduit's shape (`test_a_refused_field_is_named_so_the_form_can_say_it_there`).
    const fields = [
      { field: "provider.api_base", words: "the provider's address must be https://, so case content is encrypted" },
      { field: "provider.roles.extraction", words: "the extraction model is not a model name" },
    ];
    const detail = `${fields.map((f) => `${f.field}: ${f.words}`).join("; ")}. Nothing was checked.`;
    stub((path, init) => (path === "/v1/admin/models/checks" ? { status: 422, body: { detail: { error: "check_refused", detail, fields } } } : listed(LISTED)(path, init)));
    await openAdd();
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "azure" } });
    fireEvent.change(screen.getByLabelText("Address (https://)"), { target: { value: "http://ai.example" } });
    fireEvent.change(screen.getByLabelText("Extraction and Ask: model name"), { target: { value: "my deployment" } });
    fireEvent.change(screen.getByLabelText(/^Key/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    await screen.findByRole("alert");
    for (const [label, words] of [["Address (https://)", fields[0]!.words], ["Extraction and Ask: model name", fields[1]!.words]] as const) {
      const input = screen.getByLabelText(label);
      expect(input.getAttribute("aria-invalid")).toBe("true");
      const ids = input.getAttribute("aria-describedby")!.split(" ");
      expect(ids.map((i) => document.getElementById(i)!.textContent)).toContain(words);
    }
  });

  it("sends the label the preview shows, the provider's own when the field is emptied", async () => {
    const sent = stub((path, init) => (path === "/v1/admin/models/checks" ? { status: 200, body: PASSED } : listed(LISTED)(path, init)));
    await openAdd();
    fireEvent.change(screen.getByLabelText("Label analysts see"), { target: { value: "" } });
    expect(screen.getByText(/^Analysts will see:/).textContent).toMatch(/^Analysts will see: Google Gemini \(no contract\)/);
    fireEvent.change(screen.getByLabelText("Extraction and Ask: model name"), { target: { value: "gemini-3.8-flash" } });
    fireEvent.change(screen.getByLabelText(/^Key/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    await screen.findByRole("button", { name: "Add the engine" });
    expect(JSON.parse(sent.find((s) => s.path === "/v1/admin/models/checks")!.body).provider.label).toBe("Google Gemini");
  });

  it("offers no Cancel while a check is out, so none can pass unseen after the form has closed", async () => {
    let answer: (value: Response) => void = () => undefined;
    stub(listed(LISTED));
    const fetched = globalThis.fetch as unknown as ReturnType<typeof vi.fn<(url: string, init?: RequestInit) => Promise<Response>>>;
    const plain = fetched.getMockImplementation()!;
    fetched.mockImplementation(async (url: string, init?: RequestInit) =>
      new URL(String(url)).pathname === "/v1/admin/models/checks" ? new Promise<Response>((r) => (answer = r)) : plain(url, init),
    );
    await openAdd();
    fireEvent.change(screen.getByLabelText("Extraction and Ask: model name"), { target: { value: "gemini-3.8-flash" } });
    fireEvent.change(screen.getByLabelText(/^Key/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    expect((screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement).disabled).toBe(true);
    answer({ ok: true, status: 200, json: async () => PASSED } as Response);
    await screen.findByRole("button", { name: "Add the engine" });
    expect((screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("says one thing at a time while it adds, in one live region, never the check's words beside it", async () => {
    let answer: (value: Response) => void = () => undefined;
    stub((path, init) => (path === "/v1/admin/models/checks" ? { status: 200, body: PASSED } : listed(LISTED)(path, init)));
    const fetched = globalThis.fetch as unknown as ReturnType<typeof vi.fn<(url: string, init?: RequestInit) => Promise<Response>>>;
    const plain = fetched.getMockImplementation()!;
    fetched.mockImplementation(async (url: string, init?: RequestInit) =>
      new URL(String(url)).pathname === "/v1/admin/models/checks/chk-1/add" ? new Promise<Response>((r) => (answer = r)) : plain(url, init),
    );
    await openAdd();
    fireEvent.change(screen.getByLabelText("Extraction and Ask: model name"), { target: { value: "gemini-3.8-flash" } });
    fireEvent.change(screen.getByLabelText(/^Key/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    fireEvent.click(await screen.findByRole("button", { name: "Add the engine" }));
    expect(screen.getAllByRole("status").map((s) => s.textContent)).toEqual(["Adding…"]);
    answer({ ok: true, status: 200, json: async () => ADDED } as Response);
    await screen.findByText(/Google Gemini is added and offered to analysts/);
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("keeps your own gateway's model names whole, its prefix being only LiteLLM's way to it", async () => {
    const sent = stub((path, init) => (path === "/v1/admin/models/checks" ? { status: 200, body: { ...PASSED, engine: "gateway" } } : listed(LISTED)(path, init)));
    await openAdd();
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "gateway" } });
    fireEvent.change(screen.getByLabelText("Address (https://)"), { target: { value: "https://ai.example/v1" } });
    fireEvent.change(screen.getByLabelText("Extraction and Ask: model name"), { target: { value: "openai/gpt-4o" } });
    fireEvent.change(screen.getByLabelText(/^Token/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Check" }));
    await screen.findByRole("button", { name: "Add the engine" });
    const body = JSON.parse(sent.find((s) => s.path === "/v1/admin/models/checks")!.body);
    expect(body.provider).toMatchObject({ name: "gateway", kind: "gateway", auth: "key", roles: { extraction: "openai/gpt-4o" } });
  });

  // ADR-135 Amendment 4: an engine signed in by the gateway's own IAM role keeps no key.
  const BEDROCK = { name: "bedrock", label: "Bedrock (London)", kind: "bedrock", auth: "iam_role", region: "eu-west-2", roles: { extraction: "anthropic.claude-3-haiku" }, api_base: null, privacy_contract: false, contract_reference: null };
  const BY_ROLE = { ...CLOUD_LISTED, engines: [{ provider: BEDROCK, key_state: "iam_role", key_set_at: null, key_set_by: null, default_for: [] }] };

  it("offers no key field or key action for an engine signed in by the IAM role", async () => {
    stub((path) => (path === "/v1/admin/models" ? { status: 200, body: BY_ROLE } : undefined));
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    expect(await screen.findByText("IAM role: no key kept")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /key for Bedrock/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Test the connection to Bedrock (London)" })).toBeTruthy();
  });

  it("saves each job's default engine", async () => {
    const sent = stub(() => undefined);
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.change(await screen.findByLabelText("Extraction and Ask"), { target: { value: "gemini" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the defaults" }));
    await waitFor(() => expect(sent.some((s) => s.path === "/v1/admin/models/defaults")).toBe(true));
    expect(JSON.parse(sent.find((s) => s.path === "/v1/admin/models/defaults")!.body)).toEqual({ defaults: { extraction: "gemini" } });
  });

  // The owner's ruling 19: an edit is checked too.
  const editPuts = (sent: { path: string; method: string; body: string }[]) =>
    sent.filter((s) => s.method === "PUT" && s.path === "/v1/admin/models/engines/gemini");

  it("asks the key with a changed address, checks the edit before saving, and sends the key once", async () => {
    const sent = stub((path) => (path === "/v1/admin/models" || path === "/v1/admin/models/engines/gemini" ? { status: 200, body: SET } : undefined));
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Gemini" }));
    expect(screen.queryByLabelText(/^Key for the new address/)).toBeNull();
    expect(screen.getByRole("button", { name: "Save the engine" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/^Address/), { target: { value: "https://proxy.example.org/v1" } });
    const key = screen.getByLabelText(/^Key for the new address/) as HTMLInputElement;
    expect(key.type).toBe("password");
    expect(key.getAttribute("autocomplete")).toBe("new-password");
    const save = screen.getByRole("button", { name: "Check and save" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(screen.getByText(/checked with one small call before it is saved/)).toBeTruthy();
    fireEvent.change(key, { target: { value: PLANTED } });
    fireEvent.click(save);
    await screen.findByText(/Gemini is checked and saved/);
    const puts = editPuts(sent);
    expect(puts).toHaveLength(1);
    expect(JSON.parse(puts[0]!.body)).toMatchObject({ provider: { name: "gemini", api_base: "https://proxy.example.org/v1" }, key: PLANTED });
    expect(document.body.innerHTML).not.toContain(PLANTED);
    expect(document.body.innerHTML).not.toMatch(/key was removed/);
  });

  it("checks a changed model name with no key asked, and saves a label alone as before", async () => {
    const sent = stub((path) => (path === "/v1/admin/models" ? { status: 200, body: SET } : undefined));
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Gemini" }));
    fireEvent.change(screen.getByLabelText("Label analysts see"), { target: { value: "Google" } });
    expect(screen.getByRole("button", { name: "Save the engine" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Extraction and Ask: the provider's model"), { target: { value: "gemini-2.5-pro" } });
    expect(screen.queryByLabelText(/^Key for the new address/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Check and save" }));
    await screen.findByText(/Google is checked and saved/);
    const body = JSON.parse(editPuts(sent)[0]!.body) as Record<string, unknown>;
    expect(body).not.toHaveProperty("key");
  });

  it("shows the Conduit's refusal of an edit in its words, the engine kept as it was", async () => {
    const words = "The provider accepted the key but does not offer this model to it. Check the model name. Nothing was changed: Gemini keeps its models, address and key.";
    stub((path, init) =>
      path === "/v1/admin/models" ? { status: 200, body: SET }
        : path === "/v1/admin/models/engines/gemini" && init?.method === "PUT" ? { status: 422, body: { detail: { error: "model_admin_refused", detail: words } } }
          : undefined,
    );
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Gemini" }));
    fireEvent.change(screen.getByLabelText("Extraction and Ask: the provider's model"), { target: { value: "gemini-nope" } });
    fireEvent.click(screen.getByRole("button", { name: "Check and save" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Nothing was changed");
  });

  it("says a new key is checked before it replaces the one held", async () => {
    stub((path) => (path === "/v1/admin/models" ? { status: 200, body: SET } : undefined));
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Rotate key for Gemini" }));
    expect(screen.getByText(/checked against each of the engine's models before it replaces the one held/)).toBeTruthy();
  });

  it("replaces a held key with one action and removes it with another, each with its own route and words", async () => {
    const sent = stub((path, init) =>
      path === "/v1/admin/models"
        ? { status: 200, body: SET }
        : path === "/v1/admin/models/engines/gemini/key" && init?.method === "PUT"
          ? { status: 200, body: SET }
          : path === "/v1/admin/models/engines/gemini/key" && init?.method === "DELETE"
            ? { status: 200, body: VIEW }
            : undefined,
    );
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    const replace = await screen.findByRole("button", { name: "Rotate key for Gemini" });
    const remove = screen.getByRole("button", { name: "Remove key for Gemini" });
    expect(replace).not.toBe(remove);
    // Replacing asks for a new key and sends it once; nothing is removed.
    fireEvent.click(replace);
    const field = screen.getByLabelText(/New key for Gemini/) as HTMLInputElement;
    expect(field.value).toBe("");
    fireEvent.change(field, { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Rotate the key" }));
    await screen.findByText(/the key is set/);
    expect(sent.filter((s) => s.method === "DELETE")).toEqual([]);
    expect(sent.filter((s) => s.method === "PUT").map((s) => s.body)).toEqual([JSON.stringify({ key: PLANTED })]);
    // Removing sends no key at all, and says it is removed.
    fireEvent.click(await screen.findByRole("button", { name: "Remove key for Gemini" }));
    await screen.findByText(/the key is removed/);
    const deletes = sent.filter((s) => s.method === "DELETE");
    expect(deletes).toEqual([{ path: "/v1/admin/models/engines/gemini/key", method: "DELETE", body: "" }]);
    expect(sent.filter((s) => s.method === "PUT")).toHaveLength(1);
  });

  it("empties the key field after a refusal as it does after a save, and shows no key anywhere", async () => {
    const written: unknown[][] = [];
    for (const level of ["log", "info", "warn", "error", "debug"] as const) {
      vi.spyOn(console, level).mockImplementation((...args: unknown[]) => void written.push(args));
    }
    stub((path, init) =>
      path === "/v1/admin/models/engines/gemini/key" && init?.method === "PUT"
        ? { status: 502, body: { detail: { error: "key_refused", detail: "The model gateway refused the key. Nothing was changed." } } }
        : undefined,
    );
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Enter key for Gemini" }));
    fireEvent.change(screen.getByLabelText(/Key for Gemini/), { target: { value: PLANTED } });
    fireEvent.click(screen.getByRole("button", { name: "Set the key" }));
    await screen.findByRole("alert");
    // No field holds it, whether the form stays open or closes: its value, an attribute, a title,
    // an aria label, the address, the page's text and the console.
    for (const input of Array.from(document.querySelectorAll("input"))) {
      expect((input as HTMLInputElement).value).not.toContain(PART);
    }
    for (const element of Array.from(document.querySelectorAll("*"))) {
      for (const attribute of Array.from(element.attributes)) {
        expect(attribute.value).not.toContain(PART);
      }
    }
    expect(document.title + location.href + document.body.textContent).not.toContain(PART);
    expect(JSON.stringify(written)).not.toContain(PART);
    vi.restoreAllMocks();
  });

  it("says a key is set or there is none, and nothing else of the key", async () => {
    stub((path) => (path === "/v1/admin/models" ? { status: 200, body: SET } : undefined));
    const { unmount } = render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    const held = within(await screen.findByRole("table", { name: "Engines" }));
    expect(held.getByText(/^Key set/)).toBeTruthy();
    // Who set it and when is the record's, not the key's: nothing of its length, shape or end.
    expect(held.queryByText(/characters|length|ends in|…|\*\*\*|sk-/i)).toBeNull();
    unmount();
    stub(() => undefined);
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    const none = within(await screen.findByRole("table", { name: "Engines" }));
    expect(none.getByText("No key")).toBeTruthy();
    expect(none.queryByRole("button", { name: "Remove key for Gemini" })).toBeNull();
  });

  it("keeps an engine's kind fixed when it is edited", async () => {
    stub((path) => (path === "/v1/admin/models" ? { status: 200, body: BY_ROLE } : undefined));
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Bedrock (London)" }));
    const kind = screen.getByLabelText("Kind of engine") as HTMLInputElement;
    expect(kind.tagName).toBe("INPUT");
    expect(kind.readOnly).toBe(true);
  });

  it("offers no engine to add on a local-only deployment, and says why", async () => {
    stub((path) => (path === "/v1/admin/models" ? { status: 200, body: { ...VIEW, engines: [], local_only: true } } : undefined));
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    expect(await screen.findByText(/This deployment is local only/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add an engine" })).toBeNull();
  });
});

// ADR-135 Amendment 5 decision 2 and Amendment 9 (P12 part 2): the extraction engine is chosen at
// set-up and shown here read-only on the cloud-platform profile (the one that offers Laurium), with
// how it is changed there (Amendment 8's words); nothing on the page changes it.
describe("Models' extraction engine", () => {
  const CLOUD = { engine_kinds: ["provider", "gateway", "bedrock"] };
  it.each([
    ["laurium", "Laurium"],
    ["deep_read", "OspreyFlow Deep read"],
  ])("names %s as chosen at set-up, with how to change it, and offers no control for it", async (engine, name) => {
    stub((path) => (path === "/v1/admin/models" ? { status: 200, body: { ...VIEW, ...CLOUD, extraction_engine: engine } } : undefined));
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    const said = await screen.findByText(new RegExp(`Extraction engine: ${name}`));
    expect(said.textContent).toContain(
      "chosen at set-up: change it in osprey.yaml, re-render, and have the platform team apply it.",
    );
    expect(screen.queryByRole("combobox", { name: /extraction engine/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /extraction engine/i })).toBeNull();
    expect(screen.queryByRole("radio", { name: /laurium|deep read/i })).toBeNull();
  });

  it("says nothing of it on a profile that offers no Laurium", async () => {
    stub((path) => (path === "/v1/admin/models" ? { status: 200, body: { ...VIEW, extraction_engine: "deep_read" } } : undefined));
    render(<Models api={{ apiBaseUrl: "http://api", bearerToken: "t" }} />);
    await screen.findByText(/Settings come from/);
    expect(screen.queryByText(/Extraction engine:/)).toBeNull();
  });
});
