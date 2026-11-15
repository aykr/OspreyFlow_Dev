// Admin › Models' keyboard and accessibility harness (ADR-135 Amendment 2; `CLAUDE.md` rule 13).
// The Conduit is stood in for by an in-memory answerer that records every request
// (`window.modelsAsked`), so `admin-models.spec.ts` proves each action reached its route, and the
// every-harness axe scan sees a populated screen. Synthetic (rule 9): no real key, no real provider.
// `?open=add`, `?open=key` and `?open=limits` draw the forms open; `?local=1` a local-only deployment;
// `?usage=chosen` the usage's own days drawn; `?usage=fail` the gateway not giving its usage.
// Usage and limits (ADR-135 Amendment 3) are answered from the same in-memory record.
// ADR-135 Amendment 14: the add form's provider list and the check before Add. A key containing
// "refuse" is refused; any other passes. `held=1` draws a passed check waiting for Add;
// `check=passed` or `check=refused` fills the add form and checks it; `kind=<provider id>` chooses
// that provider in the add form. The key is never kept here, nor in `modelsSent`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import "../src/admin/admin.css";
import { Models } from "../src/admin/sections/Models";
import { applyHarnessBrand } from "./brandHarness";

await applyHarnessBrand();

const params = new URLSearchParams(location.search);
type Engine = {
  provider: { name: string; label: string | null; roles: Record<string, string>; api_base: string | null;
              privacy_contract: boolean; contract_reference: string | null; kind?: string; auth?: string | null };
  key_state: "set" | "none" | "lost" | "iam_role";
  key_set_at: string | null;
  key_set_by: string | null;
  default_for: string[];
  limits?: Record<string, number | string | null>;
};  // prettier-ignore
const engines: Engine[] = [
  { provider: { name: "gemini", label: "Gemini", roles: { extraction: "gemini-2.5-flash" }, api_base: null,
                privacy_contract: false, contract_reference: null },
    key_state: "set", key_set_at: "2026-11-08T09:00:00Z", key_set_by: "admin-1", default_for: [],
    limits: { requests_per_minute: 60, tokens_per_minute: null, budget_tokens: 2000000, budget_period: "month" } },
  { provider: { name: "openai", label: "OpenAI", roles: { extraction: "gpt-4o-mini", vision: "gpt-4o" }, api_base: null,
                privacy_contract: true, contract_reference: "DPA 2026/07" },
    key_state: "lost", key_set_at: "2026-11-01T09:00:00Z", key_set_by: "admin-1", default_for: [] },
];  // prettier-ignore
// ADR-135 Amendment 4: `iam=1` adds Bedrock in London, signed in by the gateway's own IAM role.
if (params.get("iam")) {
  engines.push({ provider: { name: "bedrock", label: "Bedrock (London)", roles: { extraction: "anthropic.claude-3-haiku" },
                             api_base: null, privacy_contract: false, contract_reference: null, kind: "bedrock", auth: "iam_role" },
                 key_state: "iam_role", key_set_at: null, key_set_by: null, default_for: [] });
}  // prettier-ignore
let defaults: Record<string, string> = {};
// The providers each profile offers (`services/api/model_catalogue.py`), Bedrock on the cloud platform alone.
const ALL3 = ["extraction", "vision", "transcription"];
const providers = [
  { id: "gemini", label: "Google Gemini", kind: "provider", address: "https://generativelanguage.googleapis.com", address_asked: false, key: true, example: "gemini-3.8-flash", jobs: ALL3, prefix: "gemini", note: "" },
  { id: "openai", label: "OpenAI", kind: "provider", address: "https://api.openai.com", address_asked: false, key: true, example: "gpt-6.1-sol", jobs: ALL3, prefix: "openai", note: "" },
  { id: "anthropic", label: "Anthropic", kind: "provider", address: "https://api.anthropic.com", address_asked: false, key: true, example: "claude-sonnet-5-5", jobs: ["extraction", "vision"], prefix: "anthropic", note: "" },
  { id: "azure", label: "Azure OpenAI", kind: "provider", address: null, address_asked: true, key: true, example: null, jobs: ALL3, prefix: "azure", note: "Give your Azure OpenAI resource's address, and each deployment's name." },
  ...(params.get("cloud") ? [{ id: "bedrock", label: "Amazon Bedrock", kind: "bedrock", address: null, address_asked: false, key: false, example: "amazon.nova-pro-v1:0", jobs: ["extraction", "vision"], prefix: "bedrock", note: "Amazon Bedrock is reached by this deployment's own role, in London only: no key and no address." }] : []),
  { id: "gateway", label: "Another provider or your own gateway", kind: "gateway", address: null, address_asked: true, key: true, example: null, jobs: ALL3, prefix: "openai", note: "Give its address (https://…). Its models are named, and each is checked by one call." },
];  // prettier-ignore
type Held = { id: string; provider: Engine["provider"]; at: string };
const held: Held[] = params.get("held")
  ? [{ id: "chk-held", provider: { name: "anthropic", label: "Anthropic", roles: { extraction: "claude-sonnet-5-5" }, api_base: null, privacy_contract: false, contract_reference: null }, at: "2026-11-15T12:00:00Z" }]
  : [];  // prettier-ignore
let checks = 0;
const history = [
  { at: "2026-11-08T09:00:00Z", by: "admin-1", action: "key_set", engine: "gemini", changes: {}, outcome: "done" },
];
const asked: string[] = [];
(window as unknown as { modelsAsked: string[] }).modelsAsked = asked;
// Each request's body, so a keyboard case can say what reached the Conduit, not only that it was asked.
const sentBodies: { request: string; body: Record<string, unknown> }[] = [];
(window as unknown as { modelsSent: typeof sentBodies }).modelsSent = sentBodies;

const view = () => ({
  engines: params.get("local") ? [] : engines.map((e) => ({ ...e, default_for: Object.keys(defaults).filter((r) => defaults[r] === e.provider.name) })),
  defaults,
  local_models: { extraction: "qwen2.5:7b-instruct", vision: "moondream:1.8b-v2-q4_K_M", transcription: "Systran/faster-whisper-tiny.en", embedding: "all-minilm:22m-l6-v2-fp16" },
  local_only: Boolean(params.get("local")),
  sendable_handling_codes: ["O"],
  source: "models file",
  // ADR-135 Amendment 7 decision 1: `cloud=1` is the cloud-platform profile, which offers the two kinds.
  engine_kinds: params.get("cloud") ? ["provider", "gateway", "bedrock"] : ["provider"],
  // ADR-135 Amendment 9: `engine=laurium`, the extraction engine the render chose (read-only).
  extraction_engine: params.get("engine") === "laurium" ? "laurium" : "deep_read",
  providers,
  checks: held.map((h) => ({ id: h.id, engine: h.provider.name, label: h.provider.label ?? h.provider.name, by: "admin-1", at: h.at, expires_at: "2026-11-15T12:15:00Z" })),
});

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const path = new URL(String(input)).pathname.replace("/v1/admin/models", "");
  const method = init?.method ?? "GET";
  asked.push(`${method} ${path || "/"}`);
  const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
  // Never a key: a key's own PUT is not recorded, and a check's body is recorded without its key.
  const { key: typedKey, ...kept } = body as { key?: string } & Record<string, unknown>;
  if (init?.body && !path.endsWith("/key")) sentBodies.push({ request: `${method} ${path || "/"}`, body: kept });
  const reply = (status: number, value: unknown) => new Response(JSON.stringify(value), { status });
  if (path === "/history") return reply(200, { entries: history });
  if (path === "/usage" && params.get("usage") === "fail") {
    return reply(502, { detail: { error: "model_usage_unavailable", detail: "The model gateway could not be reached, so its usage cannot be read now." } });
  }
  if (path === "/usage") {
    const query = new URL(String(input)).searchParams;
    asked[asked.length - 1] = `GET /usage?start=${query.get("start")}&end=${query.get("end")}`;
    const figures = (calls: number, tokens: number) => ({ calls, succeeded: calls - 1, failed: 1, prompt_tokens: tokens - 200, completion_tokens: 200, tokens });
    return reply(200, {
      start: query.get("start"), end: query.get("end"),
      rows: [
        { engine: "local", engine_label: "This deployment's own model", job: "extraction", figures: figures(40, 52000) },
        { engine: "gemini", engine_label: "Gemini", job: "extraction", figures: figures(12, 9100) },
      ],
      by_engine: {}, by_job: {}, total: figures(52, 61100),
    });
  }  // prettier-ignore
  if (path === "" && method === "GET") return reply(200, view());
  if (path === "/engines" && method === "POST") {
    // ADR-135 Amendment 4: an engine signed in by the gateway's own IAM role has no key to set.
    const provider = body.provider as Engine["provider"];
    engines.push({ provider, key_state: provider.auth === "iam_role" ? "iam_role" : "none", key_set_at: null, key_set_by: null, default_for: [] });
    return reply(200, view());
  }
  if (path === "/checks" && method === "POST") {
    const provider = body.provider as Engine["provider"];
    const models = [...new Set(Object.values(provider.roles))];
    if (String(typedKey ?? "").includes("refuse")) {
      return reply(200, { engine: provider.name, ok: false, check: null, words: "The provider refused the key. Nothing was kept: correct it and check again.",
        models: models.map((model) => ({ model, roles: Object.keys(provider.roles).filter((r) => provider.roles[r] === model), outcome: "key_refused", ok: false, words: "The provider refused the key." })) });
    }  // prettier-ignore
    const id = `chk-${++checks}`;
    held.push({ id, provider, at: "2026-11-15T12:00:00Z" });
    return reply(200, { engine: provider.name, ok: true, check: id, words: "The key and every model answered. Add the engine within 15 minutes to offer it to analysts.",
      models: models.map((model) => ({ model, roles: Object.keys(provider.roles).filter((r) => provider.roles[r] === model), outcome: "ok", ok: true, words: "Connected: the engine answered." })) });
  }  // prettier-ignore
  const checkMatch = /^\/checks\/([^/]+)(\/add)?$/.exec(path);
  if (checkMatch) {
    const pending = held.find((h) => h.id === decodeURIComponent(checkMatch[1]));
    if (!pending) return reply(404, { detail: { detail: "There is no such check. Check the key and models again." } });
    held.splice(held.indexOf(pending), 1);
    if (checkMatch[2]) {
      const iam = pending.provider.auth === "iam_role";
      engines.push({ provider: pending.provider, key_state: iam ? "iam_role" : "set", key_set_at: iam ? null : "2026-11-15T12:00:00Z", key_set_by: iam ? null : "admin-1", default_for: [] });
    }  // prettier-ignore
    return reply(200, view());
  }
  if (path === "/defaults") {
    defaults = body.defaults as Record<string, string>;
    return reply(200, view());
  }
  const match = /^\/engines\/([^/]+)(\/key|\/test|\/limits)?$/.exec(path);
  const engine = match ? engines.find((e) => e.provider.name === decodeURIComponent(match[1])) : undefined;
  if (!match || !engine) return reply(404, { detail: { detail: "There is no engine of that name." } });
  if (match[2] === "/test") {
    return reply(200, { engine: engine.provider.name, outcome: "ok", ok: true, words: "Connected: the engine answered." });
  }
  if (match[2] === "/limits") {
    engine.limits = body.limits as Engine["limits"];
    return reply(200, view());
  }
  if (match[2] === "/key") {
    // The key is never kept here either: only that one was sent.
    if (method === "PUT") Object.assign(engine, { key_state: "set", key_set_at: "2026-11-08T10:00:00Z", key_set_by: "admin-1" });
    else Object.assign(engine, { key_state: "none", key_set_at: null, key_set_by: null });
    return reply(200, view());
  }
  if (method === "PUT") engine.provider = body.provider as Engine["provider"];
  if (method === "DELETE") engines.splice(engines.indexOf(engine), 1);
  return reply(200, view());
};

createRoot(document.getElementById("root")!).render(
  <section className="admin-section" aria-label="Models">
    <h2>Models</h2>
    <Models api={{ apiBaseUrl: "http://keyboard-test.invalid", bearerToken: "unused" }} />
  </section>,
);

if (params.get("usage") === "chosen") {
  for (let i = 0; i < 40; i++) {
    const period = document.getElementById("usage-period") as HTMLSelectElement | null;
    if (period) {
      const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
      setter.call(period, "chosen");
      period.dispatchEvent(new Event("change", { bubbles: true }));
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}

const open = params.get("open");
if (open) {
  const name = open === "add" ? "Add an engine" : open === "limits" ? "Set limits for Gemini" : "Enter key for OpenAI";
  for (let i = 0; i < 40; i++) {
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.getAttribute("aria-label") === name);
    if (button) {
      button.click();
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  // `kind=bedrock` or `kind=gateway`: the add form with that provider chosen (ADR-135 Am 4, Am 14).
  const kind = params.get("kind");
  for (let i = 0; kind && i < 40; i++) {
    const select = document.getElementById("add-engine-provider") as HTMLSelectElement | null;
    if (select) {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(select, kind);
      select.dispatchEvent(new Event("change", { bubbles: true }));
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}

// `check=passed` or `check=refused`: the add form filled and checked, for the axe scan of each answer.
const checkState = params.get("check");
if (open === "add" && checkState) {
  const set = (id: string, value: string) => {
    const field = document.getElementById(id) as HTMLInputElement;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  };
  for (let i = 0; i < 40 && !document.getElementById("add-engine-key"); i++) await new Promise((r) => setTimeout(r, 50));
  set("add-engine-extraction", "gemini-3.8-flash");
  set("add-engine-key", checkState === "refused" ? "synthetic-refuse-key" : "synthetic-pass-key");
  await new Promise((r) => setTimeout(r, 50));
  (document.querySelector('form[aria-label="Add an engine"]') as HTMLFormElement).requestSubmit();
}
