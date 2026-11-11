// Admin › Running › Models (`06_DECISIONS.md` ADR-135 Amendment 2, ADR-112 Amendment 7): the model
// engines outside this deployment, each job's default engine and each engine's key. Behind
// `manage_models`. A key is typed into a write-only field, sent once, and cleared: nothing here
// ever holds or shows one, and nothing the Conduit answers carries one.
import { useCallback, useEffect, useState, type FormEvent } from "react";

import type {
  AdminEngine,
  ModelAdminEntry,
  ModelsAdminView,
} from "../../../../../packages/schemas/generated";

type ModelProviderConfig = AdminEngine["provider"];
import { Button, Checkbox, Input, Select } from "../../design/primitives";
import "./Models.css";
import {
  addEngine,
  editEngine,
  readHistory,
  readModels,
  readUsage,
  removeEngine,
  removeKey,
  setDefaults,
  setKey,
  setLimits,
  testConnection,
  type ModelsApi,
} from "./ModelsApi";
import { LimitsForm, ModelsUsage, limitsInWords } from "../../models/ModelsUsage";

/** The jobs an engine outside the deployment may take. Embeddings never leave it (ADR-135). */
const JOBS = [
  { role: "extraction", label: "Extraction and Ask" },
  { role: "vision", label: "Image description" },
  { role: "transcription", label: "Transcription" },
] as const;
const ALL_JOBS = [...JOBS, { role: "embedding", label: "Embeddings" }] as const;
// `bedrock` is LiteLLM's Bedrock provider by its key on every profile but cloud-platform, where Bedrock is its own kind.
const PROVIDERS = ["gemini", "openai", "anthropic", "azure", "bedrock"];
const KEY_WORDS: Record<AdminEngine["key_state"], string> = {
  set: "Key set",
  none: "No key",
  lost: "Key lost: enter it again",
  iam_role: "IAM role: no key kept",
};

// ADR-135 Amendment 4: what an engine is, and how it signs in.
type Kind = "provider" | "gateway" | "bedrock";
type Auth = "key" | "iam_role";
const KINDS: { kind: Kind; label: string }[] = [
  { kind: "provider", label: "A model provider (Gemini, OpenAI, Anthropic, Azure)" },
  { kind: "gateway", label: "Your organisation's own AI gateway (OpenAI-compatible)" },
  { kind: "bedrock", label: "Amazon Bedrock in London, by the namespace's IAM role" },
];

interface Draft {
  kind: Kind;
  auth: Auth;
  name: string;
  label: string;
  roles: Record<string, string>;
  api_base: string;
  privacy_contract: boolean;
  contract_reference: string;
}

const EMPTY: Draft = { kind: "provider", auth: "key", name: "gemini", label: "", roles: {}, api_base: "", privacy_contract: false, contract_reference: "" };

/** A kind chosen in the add form: its name, sign-in and address as that kind takes them. */
function withKind(draft: Draft, kind: Kind): Draft {
  if (kind === "bedrock") return { ...draft, kind, auth: "iam_role", name: "bedrock", api_base: "" };
  if (kind === "gateway") return { ...draft, kind, auth: "key", name: "" };
  return { ...draft, kind, auth: "key", name: "gemini" };
}

/** The kinds the deployment's profile takes (ADR-135 Amendment 7): a provider alone where the view says none. */
function kindsOf(view: ModelsAdminView): Kind[] {
  return (view.engine_kinds as Kind[] | undefined) ?? ["provider"];
}

/** How an engine of `kind` signs in: Bedrock by the namespace's IAM role, any other by its key or token. */
function authFor(kind: Kind): Auth {
  return kind === "bedrock" ? "iam_role" : "key";
}

function draftOf(provider: ModelProviderConfig): Draft {
  return {
    kind: (provider.kind ?? "provider") as Kind,
    auth: (provider.auth ?? "key") as Auth,
    name: provider.name,
    label: provider.label ?? "",
    roles: { ...provider.roles },
    api_base: provider.api_base ?? "",
    privacy_contract: provider.privacy_contract ?? false,
    contract_reference: provider.contract_reference ?? "",
  };
}

function providerOf(draft: Draft): ModelProviderConfig {
  const roles = Object.fromEntries(Object.entries(draft.roles).filter(([, model]) => model.trim() !== ""));
  return {
    name: draft.name.trim(),
    label: draft.label.trim() || null,
    roles,
    api_base: draft.kind === "bedrock" ? null : draft.api_base.trim() || null,
    privacy_contract: draft.privacy_contract,
    contract_reference: draft.privacy_contract ? draft.contract_reference.trim() || null : null,
    // A provider is sent as before Amendment 4; only the cloud-platform profile's two kinds name theirs.
    ...(draft.kind === "provider" ? {} : { kind: draft.kind, auth: authFor(draft.kind) }),
  };
}

function when(at: string | null | undefined): string {
  return at ? new Date(at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "";
}

/** The engine form: add (a provider name chosen) or edit (the name fixed). */
function EngineForm({
  initial,
  editing,
  kinds,
  onSave,
  onCancel,
}: {
  initial: Draft;
  editing: boolean;
  /** The kinds this deployment's profile takes (ADR-135 Amendment 7): a provider alone but on cloud-platform. */
  kinds: Kind[];
  onSave: (draft: Draft) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(initial);
  const id = editing ? `edit-${initial.name}` : "add-engine";
  // The kind is shown only where the profile offers more than a provider, or for an engine of another kind.
  const offersKinds = kinds.length > 1 || draft.kind !== "provider";
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSave(draft);
  };
  return (
    <form className="admin-models-form" aria-label={editing ? `Edit ${initial.name}` : "Add an engine"} onSubmit={submit}>
      {offersKinds && <label htmlFor={`${id}-kind`}>Kind of engine</label>}
      {!offersKinds ? null : editing ? (
        // An engine's kind is fixed once added: another kind is another processor (ADR-135 Am 2, 4).
        <Input id={`${id}-kind`} value={KINDS.find((k) => k.kind === draft.kind)?.label ?? draft.kind} readOnly aria-readonly="true" />
      ) : (
        <Select id={`${id}-kind`} value={draft.kind} onChange={(e) => setDraft(withKind(draft, e.target.value as Kind))}>
          {KINDS.filter((k) => kinds.includes(k.kind)).map((k) => (
            <option key={k.kind} value={k.kind}>
              {k.label}
            </option>
          ))}
        </Select>
      )}
      <label htmlFor={`${id}-name`}>{draft.kind === "provider" ? "Provider" : "Engine name"}</label>
      {editing || draft.kind === "bedrock" ? (
        <Input id={`${id}-name`} value={draft.name} readOnly aria-readonly="true" />
      ) : draft.kind === "gateway" ? (
        <Input
          id={`${id}-name`}
          value={draft.name}
          placeholder="lower-case, such as our_gateway"
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
      ) : (
        <Select id={`${id}-name`} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}>
          {PROVIDERS.filter((p) => p !== "bedrock" || !kinds.includes("bedrock")).map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </Select>
      )}
      {draft.kind === "gateway" && (
        <p className="label" style={{ margin: 0 }}>
          Signs in by a token, entered next and kept by the model gateway alone. Signing in by the namespace&apos;s IAM
          role waits for your gateway&apos;s owners to say how it accepts the role.
        </p>
      )}
      {draft.kind === "bedrock" && (
        <p className="label" style={{ margin: 0 }}>
          Signs in by the namespace&apos;s IAM role in London (eu-west-2); no key is kept, and no other region is used.
        </p>
      )}
      <label htmlFor={`${id}-label`}>Label analysts see</label>
      <Input id={`${id}-label`} value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} />
      {JOBS.map((job) => (
        <div key={job.role} className="admin-models-row">
          <label htmlFor={`${id}-${job.role}`}>{job.label}: the provider&apos;s model</label>
          <Input
            id={`${id}-${job.role}`}
            value={draft.roles[job.role] ?? ""}
            placeholder="none"
            onChange={(e) => setDraft({ ...draft, roles: { ...draft.roles, [job.role]: e.target.value } })}
          />
        </div>
      ))}
      {draft.kind !== "bedrock" && (
        <>
          <label htmlFor={`${id}-base`}>
            {draft.kind === "gateway" ? "Address of your gateway (https://)" : "Address (https://, where it is not the provider's own)"}
          </label>
          <Input id={`${id}-base`} value={draft.api_base} onChange={(e) => setDraft({ ...draft, api_base: e.target.value })} />
        </>
      )}
      <label className="admin-models-check">
        <Checkbox
          checked={draft.privacy_contract}
          onChange={(e) => setDraft({ ...draft, privacy_contract: e.target.checked })}
        />{" "}
        Under a privacy contract (a data-processing agreement covering this key)
      </label>
      {draft.privacy_contract && (
        <>
          <label htmlFor={`${id}-reference`}>The agreement&apos;s reference, in words</label>
          <Input
            id={`${id}-reference`}
            value={draft.contract_reference}
            onChange={(e) => setDraft({ ...draft, contract_reference: e.target.value })}
          />
        </>
      )}
      <div className="admin-models-actions">
        <Button type="submit" variant="primary">
          {editing ? "Save the engine" : "Add the engine"}
        </Button>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** The write-only key field: never filled from anything, cleared once sent. */
function KeyForm({ engine, onSend, onCancel }: { engine: AdminEngine; onSend: (key: string) => void; onCancel: () => void }) {
  const [key, setKeyText] = useState("");
  const name = engine.provider.name;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const typed = key;
    setKeyText("");
    onSend(typed);
  };
  return (
    <form className="admin-models-form" aria-label={`Key for ${name}`} onSubmit={submit}>
      <label htmlFor={`key-${name}`}>
        {engine.key_state === "set" ? "New key" : "Key"} for {engine.provider.label ?? name} (not shown, never sent back)
      </label>
      <Input
        id={`key-${name}`}
        type="password"
        autoComplete="off"
        spellCheck={false}
        value={key}
        onChange={(e) => setKeyText(e.target.value)}
      />
      <div className="admin-models-actions">
        <Button type="submit" variant="primary" disabled={key.trim() === ""}>
          {engine.key_state === "set" ? "Rotate the key" : "Set the key"}
        </Button>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function Models({ api }: { api: ModelsApi }) {
  const [view, setView] = useState<ModelsAdminView | null>(null);
  const [history, setHistory] = useState<ModelAdminEntry[]>([]);
  const [open, setOpen] = useState<{ kind: "add" } | { kind: "edit" | "key" | "limits"; name: string } | null>(null);
  const [defaults, setDefaultsDraft] = useState<Record<string, string>>({});
  const [said, setSaid] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  // One reader for the usage section for as long as the Conduit and token are the same.
  const readUsageHere = useCallback(
    (start: string, end: string) => readUsage(api, start, end),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [api.apiBaseUrl, api.bearerToken],
  );
  const refreshHistory = () => {
    readHistory(api)
      .then((h) => setHistory(h.entries))
      .catch(() => undefined);
  };
  const shown = (next: ModelsAdminView, words: string) => {
    setView(next);
    setDefaultsDraft({ ...next.defaults });
    setOpen(null);
    setSaid(words);
    refreshHistory();
  };
  const act = (work: Promise<ModelsAdminView>, words: string) => {
    setProblem(null);
    setSaid(null);
    void work.then((next) => shown(next, words)).catch((e: Error) => {
      setProblem(e.message);
      refreshHistory();
    });
  };
  useEffect(() => {
    readModels(api)
      .then((v) => {
        setView(v);
        setDefaultsDraft({ ...v.defaults });
      })
      .catch((e: Error) => setProblem(e.message));
    refreshHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);

  const test = (name: string) => {
    setProblem(null);
    setSaid(null);
    void testConnection(api, name)
      .then((result) => {
        setSaid(`${name}: ${result.words}`);
        refreshHistory();
      })
      .catch((e: Error) => setProblem(e.message));
  };

  return (
    <>
      <p className="label" style={{ margin: 0 }}>
        Engines outside this deployment that analysts may choose, each job&apos;s default engine, each engine&apos;s key
        and limits, and how much each is used. A key is kept by the model gateway alone: it is never shown again, never
        sent back and never in the audit log. Every change is recorded there.
      </p>
      {problem && <p role="alert">{problem}</p>}
      {said && <p role="status">{said}</p>}
      {!view && !problem && <p className="label">Reading the engines…</p>}
      {view && (
        <>
          <section aria-labelledby="models-declared">
            <h3 id="models-declared">What the installer declared</h3>
            <p className="label" style={{ margin: 0 }}>
              {view.local_only
                ? "This deployment is local only: no engine outside it may be added here. The installer changes that in osprey.yaml (local_only: false), then runs ospreyflow apply."
                : `Case content may leave this deployment only with handling code${view.sendable_handling_codes.length === 1 ? "" : "s"} ${view.sendable_handling_codes.join(", ") || "(none)"}, and only from a dataset whose egress allows it (Admin › Datasets).`}{" "}
              Settings come from {view.source}.
            </p>
          </section>

          <section aria-labelledby="models-engines">
            <h3 id="models-engines">Engines</h3>
            <table className="table" aria-label="Engines">
              <thead>
                <tr>
                  <th>Engine</th>
                  <th>Jobs and models</th>
                  <th>Privacy contract</th>
                  <th>Key</th>
                  <th>Limits</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>This deployment&apos;s own models</td>
                  <td>
                    {ALL_JOBS.filter((j) => view.local_models[j.role]).map((j) => (
                      <div key={j.role}>
                        {j.label}: {view.local_models[j.role]}
                      </div>
                    ))}
                  </td>
                  <td>Nothing leaves</td>
                  <td>No key needed</td>
                  <td>No limits</td>
                  <td />
                </tr>
                {view.engines.map((engine) => {
                  const name = engine.provider.name;
                  const label = engine.provider.label ?? name;
                  return (
                    <tr key={name}>
                      <td>
                        {label} <span className="label">({name})</span>
                        {engine.provider.api_base && <div className="label">{engine.provider.api_base}</div>}
                      </td>
                      <td>
                        {Object.entries(engine.provider.roles).map(([role, model]) => (
                          <div key={role}>
                            {ALL_JOBS.find((j) => j.role === role)?.label ?? role}: {model}
                          </div>
                        ))}
                      </td>
                      <td>
                        {engine.provider.privacy_contract
                          ? `Under contract${engine.provider.contract_reference ? ` (${engine.provider.contract_reference})` : ""}`
                          : "No contract"}
                      </td>
                      <td>
                        {KEY_WORDS[engine.key_state]}
                        {engine.key_state === "set" && engine.key_set_at && (
                          <div className="label">
                            {when(engine.key_set_at)}, by {engine.key_set_by}
                          </div>
                        )}
                      </td>
                      <td>{limitsInWords(engine.limits)}</td>
                      <td className="admin-models-actions">
                        <Button aria-label={`Edit ${label}`} onClick={() => setOpen({ kind: "edit", name })}>
                          Edit
                        </Button>
                        <Button aria-label={`Set limits for ${label}`} onClick={() => setOpen({ kind: "limits", name })}>
                          Set limits
                        </Button>
                        {engine.key_state !== "iam_role" && (
                          <Button
                            aria-label={`${engine.key_state === "set" ? "Rotate" : "Enter"} key for ${label}`}
                            onClick={() => setOpen({ kind: "key", name })}
                          >
                            {engine.key_state === "set" ? "Rotate key" : "Enter key"}
                          </Button>
                        )}
                        {engine.key_state !== "none" && engine.key_state !== "iam_role" && (
                          <Button
                            aria-label={`Remove key for ${label}`}
                            onClick={() => act(removeKey(api, name), `${label}: the key is removed; it is offered to no analyst until one is set.`)}
                          >
                            Remove key
                          </Button>
                        )}
                        <Button aria-label={`Test the connection to ${label}`} onClick={() => test(name)}>
                          Test the connection
                        </Button>
                        <Button
                          aria-label={`Remove ${label}`}
                          onClick={() => act(removeEngine(api, name), `${label} is removed.`)}
                        >
                          Remove
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {open?.kind === "edit" &&
              (() => {
                const engine = view.engines.find((e) => e.provider.name === open.name);
                return engine ? (
                  <EngineForm
                    key={open.name}
                    initial={draftOf(engine.provider)}
                    editing
                    kinds={kindsOf(view)}
                    onCancel={() => setOpen(null)}
                    onSave={(draft) => {
                      const hadKey = engine.key_state === "set";
                      const next = providerOf(draft);
                      const moved = (engine.provider.api_base ?? "") !== (next.api_base ?? "");
                      act(
                        editEngine(api, next),
                        hadKey && moved
                          ? `${draft.name} is saved. Its address changed, so its key was removed: a key is never sent to an address it was not entered for. Enter the key again.`
                          : `${draft.name} is saved.`,
                      );
                    }}
                  />
                ) : null;
              })()}
            {open?.kind === "key" &&
              (() => {
                const engine = view.engines.find((e) => e.provider.name === open.name);
                return engine ? (
                  <KeyForm
                    key={open.name}
                    engine={engine}
                    onCancel={() => setOpen(null)}
                    onSend={(key) =>
                      act(
                        setKey(api, engine.provider.name, key),
                        `${engine.provider.label ?? engine.provider.name}: the key is set. It is kept by the model gateway and never shown again.`,
                      )
                    }
                  />
                ) : null;
              })()}
            {open?.kind === "limits" &&
              (() => {
                const engine = view.engines.find((e) => e.provider.name === open.name);
                const label = engine?.provider.label ?? open.name;
                return engine ? (
                  <LimitsForm
                    key={open.name}
                    engine={engine}
                    onCancel={() => setOpen(null)}
                    onSave={(limits) =>
                      act(
                        setLimits(api, engine.provider.name, limits),
                        `${label}: its limits are saved; the model gateway applies them from the next call.`,
                      )
                    }
                  />
                ) : null;
              })()}
            {open?.kind === "add" ? (
              <EngineForm
                initial={EMPTY}
                editing={false}
                kinds={kindsOf(view)}
                onCancel={() => setOpen(null)}
                onSave={(draft) => {
                  const added = providerOf(draft);
                  act(
                    addEngine(api, added),
                    added.auth === "iam_role"
                      ? `${added.name} is added. It signs in by the namespace's IAM role: no key is needed.`
                      : `${added.name} is added. Enter its key next.`,
                  );
                }}
              />
            ) : (
              !view.local_only && (
                <Button onClick={() => setOpen({ kind: "add" })} aria-label="Add an engine">
                  Add an engine
                </Button>
              )
            )}
          </section>

          <section aria-labelledby="models-defaults">
            <h3 id="models-defaults">Each job&apos;s default engine</h3>
            <p className="label" style={{ margin: 0 }}>
              An analyst may choose another engine for a request. A default whose key is not set runs on this
              deployment&apos;s own model.
            </p>
            {JOBS.map((job) => (
              <div key={job.role} className="admin-models-row">
                <label htmlFor={`default-${job.role}`}>{job.label}</label>
                <Select
                  id={`default-${job.role}`}
                  value={defaults[job.role] ?? "local"}
                  onChange={(e) => setDefaultsDraft({ ...defaults, [job.role]: e.target.value })}
                >
                  <option value="local">This deployment&apos;s own model</option>
                  {view.engines
                    .filter((e) => job.role in e.provider.roles)
                    .map((e) => (
                      <option key={e.provider.name} value={e.provider.name}>
                        {e.provider.label ?? e.provider.name}
                      </option>
                    ))}
                </Select>
              </div>
            ))}
            <Button
              onClick={() =>
                act(
                  setDefaults(api, Object.fromEntries(Object.entries(defaults).filter(([, engine]) => engine !== "local"))),
                  "Each job's default engine is saved.",
                )
              }
            >
              Save the defaults
            </Button>
          </section>

          <ModelsUsage read={readUsageHere} />

          <section aria-labelledby="models-history">
            <h3 id="models-history">History</h3>
            {history.length === 0 ? (
              <p className="label" style={{ margin: 0 }}>
                Nothing has been changed here yet.
              </p>
            ) : (
              <table className="table" aria-label="Engines' history">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Who</th>
                    <th>What</th>
                    <th>Engine</th>
                    <th>Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((entry, i) => (
                    <tr key={`${entry.at}-${i}`}>
                      <td>{when(entry.at)}</td>
                      <td>{entry.by}</td>
                      <td>{entry.action.replaceAll("_", " ")}</td>
                      <td>{entry.engine ?? ""}</td>
                      <td>{entry.outcome}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </>
  );
}
