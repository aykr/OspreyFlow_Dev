// Admin › Models' keyboard and accessibility harness (ADR-135 Amendment 2; `CLAUDE.md` rule 13).
// The Conduit is stood in for by an in-memory answerer that records every request
// (`window.modelsAsked`), so `admin-models.spec.ts` proves each action reached its route, and the
// every-harness axe scan sees a populated screen. Synthetic (rule 9): no real key, no real provider.
// `?open=add` and `?open=key` draw the forms open; `?local=1` a local-only deployment.
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
              privacy_contract: boolean; contract_reference: string | null };
  key_state: "set" | "none" | "lost";
  key_set_at: string | null;
  key_set_by: string | null;
  default_for: string[];
};  // prettier-ignore
const engines: Engine[] = [
  { provider: { name: "gemini", label: "Gemini", roles: { extraction: "gemini-2.5-flash" }, api_base: null,
                privacy_contract: false, contract_reference: null },
    key_state: "set", key_set_at: "2026-11-08T09:00:00Z", key_set_by: "admin-1", default_for: [] },
  { provider: { name: "openai", label: "OpenAI", roles: { extraction: "gpt-4o-mini", vision: "gpt-4o" }, api_base: null,
                privacy_contract: true, contract_reference: "DPA 2026/07" },
    key_state: "lost", key_set_at: "2026-11-01T09:00:00Z", key_set_by: "admin-1", default_for: [] },
];  // prettier-ignore
let defaults: Record<string, string> = {};
const history = [
  { at: "2026-11-08T09:00:00Z", by: "admin-1", action: "key_set", engine: "gemini", changes: {}, outcome: "done" },
];
const asked: string[] = [];
(window as unknown as { modelsAsked: string[] }).modelsAsked = asked;

const view = () => ({
  engines: params.get("local") ? [] : engines.map((e) => ({ ...e, default_for: Object.keys(defaults).filter((r) => defaults[r] === e.provider.name) })),
  defaults,
  local_models: { extraction: "qwen2.5:7b-instruct", vision: "moondream:1.8b-v2-q4_K_M", transcription: "Systran/faster-whisper-tiny.en", embedding: "all-minilm:22m-l6-v2-fp16" },
  local_only: Boolean(params.get("local")),
  sendable_handling_codes: ["O"],
  source: "models file",
});

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const path = new URL(String(input)).pathname.replace("/v1/admin/models", "");
  const method = init?.method ?? "GET";
  asked.push(`${method} ${path || "/"}`);
  const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
  const reply = (status: number, value: unknown) => new Response(JSON.stringify(value), { status });
  if (path === "/history") return reply(200, { entries: history });
  if (path === "" && method === "GET") return reply(200, view());
  if (path === "/engines" && method === "POST") {
    engines.push({ provider: body.provider as Engine["provider"], key_state: "none", key_set_at: null, key_set_by: null, default_for: [] });
    return reply(200, view());
  }
  if (path === "/defaults") {
    defaults = body.defaults as Record<string, string>;
    return reply(200, view());
  }
  const match = /^\/engines\/([^/]+)(\/key|\/test)?$/.exec(path);
  const engine = match ? engines.find((e) => e.provider.name === decodeURIComponent(match[1])) : undefined;
  if (!match || !engine) return reply(404, { detail: { detail: "There is no engine of that name." } });
  if (match[2] === "/test") {
    return reply(200, { engine: engine.provider.name, outcome: "ok", ok: true, words: "Connected: the engine answered." });
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

const open = params.get("open");
if (open) {
  const name = open === "add" ? "Add an engine" : "Enter key for OpenAI";
  for (let i = 0; i < 40; i++) {
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.getAttribute("aria-label") === name);
    if (button) {
      button.click();
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}
