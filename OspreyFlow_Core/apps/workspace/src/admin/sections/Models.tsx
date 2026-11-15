// Admin › Running › Models (`06_DECISIONS.md` ADR-135 Amendment 2, ADR-112 Amendment 7): the model
// engines outside this deployment, each job's default engine and each engine's key. Behind
// `manage_models`. A key is typed into a write-only field, sent once, and cleared: nothing here
// ever holds or shows one, and nothing the Conduit answers carries one.
import { useCallback, useEffect, useState, type FormEvent } from "react";

import type {
  AdminEngine,
  CatalogueEntry,
  EngineCheckResult,
  ModelAdminEntry,
  ModelsAdminView,
} from "../../../../../packages/schemas/generated";

type ModelProviderConfig = AdminEngine["provider"];
import { Button, Checkbox, Input, Select } from "../../design/primitives";
import "./Models.css";
import {
  addChecked,
  cancelCheck,
  checkEngine,
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
  ModelsRefused,
  type ModelsApi,
  type RefusedField,
} from "./ModelsApi";
import { LimitsForm, ModelsUsage, limitsInWords } from "../../models/ModelsUsage";
import { engineOptionText } from "../../models/engines";

/** The jobs an engine outside the deployment may take. Embeddings never leave it (ADR-135). */
const JOBS = [
  { role: "extraction", label: "Extraction and Ask" },
  { role: "vision", label: "Image description" },
  { role: "transcription", label: "Transcription" },
] as const;
const ALL_JOBS = [...JOBS, { role: "embedding", label: "Embeddings" }] as const;
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
  { kind: "bedrock", label: "Amazon Bedrock in London, by the gateway's own IAM role" },
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

/** How an engine of `kind` signs in: Bedrock by the gateway's own IAM role, any other by its key or token. */
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
    // A provider is sent as before Amendment 4; only the other two kinds name theirs.
    ...(draft.kind === "provider" ? {} : { kind: draft.kind, auth: authFor(draft.kind) }),
  };
}

function when(at: string | null | undefined): string {
  return at ? new Date(at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "";
}

/** The edit form: an engine's label, models, address and agreement; its name and kind are fixed. */
function EngineForm({
  initial,
  keyless,
  onSave,
  onCancel,
}: {
  initial: Draft;
  /** Signed in by the gateway's own IAM role: no key is ever asked (ADR-135 Amendment 4). */
  keyless: boolean;
  /** `checked`: a changed model name or address, which the Conduit checks before saving. */
  onSave: (draft: Draft, key: string | null, checked: boolean) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(initial);
  // Write-only, as the add form's: never filled, cleared once sent.
  const [key, setKeyText] = useState("");
  const id = `edit-${initial.name}`;
  // The owner's ruling 19: a changed model name or address is checked with one small call before it
  // is saved, and a changed address takes its key with it (a key is never sent where it was not
  // entered for). A label or an agreement changed alone asks nothing.
  const moved = draft.api_base.trim() !== initial.api_base.trim();
  const held = new Set(Object.values(initial.roles).map((m) => m.trim()));
  const checked = moved || Object.values(draft.roles).some((m) => m.trim() !== "" && !held.has(m.trim()));
  const askKey = moved && !keyless;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const typed = askKey ? key : null;
    setKeyText("");
    onSave(draft, typed, checked);
  };
  return (
    <form className="admin-models-form" aria-label={`Edit ${initial.name}`} onSubmit={submit}>
      {draft.kind !== "provider" && (
        <>
          <label htmlFor={`${id}-kind`}>Kind of engine</label>
          {/* An engine's kind is fixed once added: another kind is another processor (ADR-135 Am 2, 4). */}
          <Input id={`${id}-kind`} value={KINDS.find((k) => k.kind === draft.kind)?.label ?? draft.kind} readOnly aria-readonly="true" />
        </>
      )}
      <label htmlFor={`${id}-name`}>{draft.kind === "provider" ? "Provider" : "Engine name"}</label>
      <Input id={`${id}-name`} value={draft.name} readOnly aria-readonly="true" />
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
      {askKey && (
        <>
          <label htmlFor={`${id}-key`}>
            Key for the new address (not shown, never sent back): a key is never sent where it was not entered for
          </label>
          <Input
            id={`${id}-key`}
            type="password"
            autoComplete="new-password"
            data-1p-ignore="true"
            data-lpignore="true"
            data-bwignore="true"
            data-form-type="other"
            spellCheck={false}
            value={key}
            onChange={(e) => setKeyText(e.target.value)}
          />
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
      {checked && (
        <p className="label" style={{ margin: 0 }}>
          A changed model name or address is checked with one small call before it is saved: nothing changes unless it
          answers.
        </p>
      )}
      <div className="admin-models-actions">
        <Button type="submit" variant="primary" disabled={askKey && key.trim() === ""}>
          {checked ? "Check and save" : "Save the engine"}
        </Button>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** The form's fields a refusal can be tied to. */
type Field = "label" | "address" | "key" | "reference" | `job-${string}`;
/** The form's field for a field the Conduit's rules named (`RefusedField.field`). */
function formField(named: string): Field | null {
  if (named === "provider.api_base") return "address";
  if (named === "provider.label") return "label";
  if (named === "provider.contract_reference") return "reference";
  if (named === "key") return "key";
  const job = /^provider\.roles\.(\w+)$/.exec(named);
  return job ? `job-${job[1]}` : null;
}
/** The fields a refusal in the check's own fixed words is about (`model_admin.py`'s `check`). */
function wordsFields(words: string, jobs: string[]): Field[] {
  if (words.startsWith("The label")) return ["label"];
  if (words.startsWith("The agreement reference")) return ["reference"];
  if (words.startsWith("Give the key")) return ["key"];
  if (words.startsWith("A model name looks like a key")) return jobs.map((j) => `job-${j}` as Field);
  return [];
}

/**
 * The add form (ADR-135 Amendment 14, the owner's first slice): a provider chosen from this
 * deployment's list, its label filled, its own address shown (asked for where it has none, none for
 * Bedrock), only its jobs, each model typed with a current example, its key in a write-only field,
 * and what analysts will see. **Check** proves the key and each model by one call in the gateway;
 * only a passed check can be added, and **Add** sends the check, never the key.
 */
function AddEngineForm({
  api,
  providers,
  onAdded,
  onClose,
}: {
  api: ModelsApi;
  providers: CatalogueEntry[];
  onAdded: (view: ModelsAdminView, words: string) => void;
  onClose: (view: ModelsAdminView | null, words: string | null) => void;
}) {
  const [chosen, setChosen] = useState(providers[0]?.id ?? "");
  const entry = providers.find((p) => p.id === chosen) ?? providers[0];
  const [label, setLabel] = useState(entry?.label ?? "");
  const [changing, setChanging] = useState(false);
  const [address, setAddress] = useState("");
  const [roles, setRoles] = useState<Record<string, string>>({});
  // The key is held in this field's state alone until Check sends it, then emptied: never stored.
  const [key, setKeyText] = useState("");
  const [contract, setContract] = useState(false);
  const [reference, setReference] = useState("");
  const [result, setResult] = useState<EngineCheckResult | null>(null);
  const [refused, setRefused] = useState<{ words: string; fields: RefusedField[] } | null>(null);
  const [busy, setBusy] = useState<"checking" | "adding" | null>(null);
  if (!entry) return null;
  const id = "add-engine";
  const passed = result?.ok === true && result.check !== null;
  const shown = label.trim() || entry.label;

  const choose = (next: string) => {
    const picked = providers.find((p) => p.id === next);
    setChosen(next);
    setLabel(picked?.label ?? "");
    setChanging(false);
    setAddress("");
    setRoles({});
    // A key is never sent to a provider or an address it was not typed for (Amendment 2).
    setKeyText("");
    setResult(null);
    setRefused(null);
  };
  /** The model as the provider names it: the prefix is the form's business, taken off if typed. Not
   * for your own gateway, whose prefix is only LiteLLM's way to it and whose own names may hold it. */
  const bare = (model: string) =>
    entry.kind === "gateway" ? model.trim() : model.trim().replace(new RegExp(`^${entry.prefix}/`), "");
  const engine = (): ModelProviderConfig => ({
    name: entry.id,
    // The label the preview shows is the label sent: left empty, the provider's own.
    label: shown,
    roles: Object.fromEntries(
      entry.jobs.map((job) => [job, bare(roles[job] ?? "")] as const).filter(([, model]) => model !== ""),
    ),
    api_base: entry.address_asked || changing ? address.trim() || null : null,
    privacy_contract: contract,
    contract_reference: contract ? reference.trim() || null : null,
    ...(entry.kind === "provider" ? {} : { kind: entry.kind, auth: entry.key ? "key" : "iam_role" }),
  });
  const check = (event: FormEvent) => {
    event.preventDefault();
    const typed = entry.key ? key : null;
    setKeyText(""); // cleared once sent, whatever the answer
    setResult(null);
    setRefused(null);
    setBusy("checking");
    void checkEngine(api, engine(), typed)
      .then(setResult)
      .catch((e: Error) => setRefused({ words: e.message, fields: e instanceof ModelsRefused ? e.fields : [] }))
      .finally(() => setBusy(null));
  };
  const add = () => {
    if (!passed) return;
    setBusy("adding");
    void addChecked(api, result.check!)
      .then((view) =>
        onAdded(view, `${shown} is added and offered to analysts for cases whose data may leave this deployment.`),
      )
      .catch((e: Error) => {
        setResult(null);
        setRefused({ words: e.message, fields: [] });
      })
      .finally(() => setBusy(null));
  };
  const cancel = () => {
    if (!passed) return onClose(null, null);
    void cancelCheck(api, result.check!)
      .then((view) => onClose(view, `${shown} was not added; its check and key are removed.`))
      .catch((e: Error) => setRefused({ words: e.message, fields: [] }));
  };

  // Each refusal tied to the field it is about: a key refused to the key, a model to its job.
  const fieldOf = (job: string): Field => `job-${job}`;
  const errors = new Map<Field, string>();
  for (const m of result?.ok === false ? result.models : []) {
    if (m.ok) continue;
    if (m.outcome === "key_refused" || m.outcome === "gateway_token") errors.set("key", m.words);
    else if (m.outcome === "model_not_offered" || m.outcome === "model_not_enabled")
      for (const r of m.roles) errors.set(fieldOf(r), m.words);
  }
  if (refused) {
    for (const named of refused.fields) {
      const at = formField(named.field);
      if (at) errors.set(at, named.words);
    }
    const filled = entry.jobs.filter((j) => (roles[j] ?? "").trim() !== "");
    for (const at of wordsFields(refused.words, filled)) errors.set(at, refused.words);
  }
  const errorId = (f: Field) => `${id}-${f}-error`;
  const tied = (f: Field, hint?: string) => ({
    "aria-invalid": errors.has(f) ? (true as const) : undefined,
    "aria-describedby": [hint, errors.has(f) ? errorId(f) : null].filter(Boolean).join(" ") || undefined,
  });
  const error = (f: Field) =>
    errors.has(f) ? (
      <p id={errorId(f)} className="admin-models-error">
        {errors.get(f)}
      </p>
    ) : null;
  const jobLabel = (job: string) => JOBS.find((j) => j.role === job)?.label ?? job;
  // What the analysts' engine list shows for it (`engineOptionText`), so the preview cannot drift from it.
  const preview = engineOptionText({ name: entry.id, label: shown, roles: [], default_for: [], privacy_contract: contract });

  return (
    <form className="admin-models-form" aria-label="Add an engine" autoComplete="off" onSubmit={check}>
      <fieldset disabled={passed || busy !== null} className="admin-models-fieldset">
        <label htmlFor={`${id}-provider`}>Provider</label>
        <Select id={`${id}-provider`} value={entry.id} onChange={(e) => choose(e.target.value)}>
          {providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </Select>
        {entry.note && (
          <p className="label" style={{ margin: 0 }}>
            {entry.note}
          </p>
        )}
        <label htmlFor={`${id}-label`}>Label analysts see</label>
        <Input id={`${id}-label`} value={label} onChange={(e) => setLabel(e.target.value)} {...tied("label")} />
        {error("label")}
        {entry.address && !changing && (
          <div className="admin-models-row">
            <span className="label" id={`${id}-address-shown`}>
              Address: {entry.address}
            </span>
            <Button type="button" aria-label={`Change the address of ${entry.label}`} onClick={() => setChanging(true)}>
              Change
            </Button>
          </div>
        )}
        {(entry.address_asked || changing) && (
          <>
            <label htmlFor={`${id}-address`}>
              {entry.address_asked ? "Address (https://)" : "Address of the gateway in front of it (https://)"}
            </label>
            <Input id={`${id}-address`} value={address} onChange={(e) => setAddress(e.target.value)} {...tied("address")} />
            {error("address")}
          </>
        )}
        <p className="label" id={`${id}-jobs-hint`} style={{ margin: 0 }}>
          Type each model&apos;s name as {entry.label} gives it. A job left empty uses this deployment&apos;s own model.
        </p>
        {entry.jobs.map((job) => (
          <div key={job} className="admin-models-row">
            <label htmlFor={`${id}-${job}`}>{jobLabel(job)}: model name</label>
            <Input
              id={`${id}-${job}`}
              value={roles[job] ?? ""}
              placeholder={entry.example ? `such as ${entry.example}` : undefined}
              spellCheck={false}
              onChange={(e) => setRoles({ ...roles, [job]: e.target.value })}
              {...tied(fieldOf(job), `${id}-jobs-hint`)}
            />
            {error(fieldOf(job))}
          </div>
        ))}
        {entry.key && (
          <>
            <label htmlFor={`${id}-key`}>
              {entry.kind === "gateway" ? "Token" : "Key"} (sent once to the model gateway, never shown again)
            </label>
            {/* Never filled or saved by the browser: `new-password` is the value browsers honour on a
                password field (they ignore `off` there), and the password managers' own opt-outs. */}
            <Input
              id={`${id}-key`}
              type="password"
              autoComplete="new-password"
              data-1p-ignore="true"
              data-lpignore="true"
              data-bwignore="true"
              data-form-type="other"
              spellCheck={false}
              value={key}
              onChange={(e) => setKeyText(e.target.value)}
              {...tied("key")}
            />
            {error("key")}
          </>
        )}
        <label className="admin-models-check">
          <Checkbox checked={contract} onChange={(e) => setContract(e.target.checked)} /> Under a privacy contract (a
          data-processing agreement covering this key)
        </label>
        {contract && (
          <>
            <label htmlFor={`${id}-reference`}>The agreement&apos;s reference, in words</label>
            <Input
              id={`${id}-reference`}
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              {...tied("reference")}
            />
            {error("reference")}
          </>
        )}
      </fieldset>
      <p className="admin-models-preview" id={`${id}-preview`}>
        Analysts will see: <strong>{preview}</strong>. It is offered only for cases whose data may leave this deployment.
      </p>
      {/* One live region at a time: the busy words replace the check's, never stand beside them. */}
      {busy && <p role="status">{busy === "checking" ? "Checking…" : "Adding…"}</p>}
      {result && !busy && (
        <div role={result.ok ? "status" : "alert"} className="admin-models-result">
          <p style={{ margin: 0 }}>{result.words}</p>
          {result.models.length > 1 && (
            <ul>
              {result.models.map((m) => (
                <li key={m.model}>
                  {m.model}: {m.words}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {refused && <p role="alert">{refused.words}</p>}
      <div className="admin-models-actions">
        {passed ? (
          <Button type="button" variant="primary" onClick={add} disabled={busy !== null}>
            Add the engine
          </Button>
        ) : (
          <Button type="submit" variant="primary" disabled={busy !== null || (entry.key && key.trim() === "")}>
            Check
          </Button>
        )}
        {/* Not while a check is out: it could pass after the form closed, its key unseen here. */}
        <Button type="button" onClick={cancel} disabled={busy !== null}>
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
        autoComplete="new-password"
        data-1p-ignore="true"
        data-lpignore="true"
        data-bwignore="true"
        data-form-type="other"
        spellCheck={false}
        value={key}
        onChange={(e) => setKeyText(e.target.value)}
      />
      <p className="label" style={{ margin: 0 }}>
        {engine.key_state === "set"
          ? "The new key is checked against each of the engine's models before it replaces the one held: a key the provider refuses changes nothing."
          : "The key is checked against each of the engine's models before it is kept: a key the provider refuses is not kept."}
      </p>
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
            <h2 id="models-declared" className="value">What the installer declared</h2>
            <p className="label" style={{ margin: 0 }}>
              {view.local_only
                ? "This deployment is local only: no engine outside it may be added here. The installer changes that in osprey.yaml (local_only: false), then runs ospreyflow apply."
                : `Case content may leave this deployment only with handling code${view.sendable_handling_codes.length === 1 ? "" : "s"} ${view.sendable_handling_codes.join(", ") || "(none)"}, and only from a dataset whose egress allows it (Admin › Datasets).`}{" "}
              Settings come from {view.source}.
            </p>
            {/* ADR-135 Amendments 5, 8 and 9: chosen at set-up on the cloud-platform profile (the one that
                offers Laurium, and the only one offering Bedrock), shown, not changed here. */}
            {(view.engine_kinds ?? []).includes("bedrock") && (
              <p className="label" style={{ margin: "0.5rem 0 0" }}>
                Extraction engine: {view.extraction_engine === "laurium" ? "Laurium" : "OspreyFlow Deep read"}, chosen
                at set-up: change it in osprey.yaml, re-render, and have the platform team apply it.
              </p>
            )}
          </section>

          <section aria-labelledby="models-engines">
            <h2 id="models-engines" className="value">Engines</h2>
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
                        {/* ADR-135 Amendment 8: never offered nor written into the gateway. */}
                        {engine.not_made && <div role="note">{engine.not_made}</div>}
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
                    keyless={engine.key_state === "iam_role"}
                    onCancel={() => setOpen(null)}
                    onSave={(draft, key, checked) =>
                      act(
                        editEngine(api, providerOf(draft), key ?? undefined),
                        checked ? `${draft.label || draft.name} is checked and saved.` : `${draft.name} is saved.`,
                      )
                    }
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
                        `${engine.provider.label ?? engine.provider.name}: checked, the key is set. It is kept by the model gateway and never shown again.`,
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
            {(view.checks ?? []).length > 0 && (
              <table className="table" aria-label="Being checked">
                <thead>
                  <tr>
                    <th>Being checked</th>
                    <th>Checked by</th>
                    <th>Add it before</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(view.checks ?? []).map((held) => (
                    <tr key={held.id}>
                      <td>
                        {held.label} <span className="label">({held.engine})</span>
                        <div className="label">Passed its check; not offered to analysts until it is added.</div>
                      </td>
                      <td>{held.by}</td>
                      <td>{when(held.expires_at)}</td>
                      <td className="admin-models-actions">
                        <Button
                          aria-label={`Cancel the check of ${held.label}`}
                          onClick={() =>
                            act(cancelCheck(api, held.id), `${held.label} was not added; its check and key are removed.`)
                          }
                        >
                          Cancel the check
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {open?.kind === "add" ? (
              <AddEngineForm
                api={api}
                providers={view.providers ?? []}
                onAdded={(next, words) => shown(next, words)}
                onClose={(next, words) => {
                  if (next && words) shown(next, words);
                  else setOpen(null);
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
            <h2 id="models-defaults" className="value">Each job&apos;s default engine</h2>
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
            <h2 id="models-history" className="value">History</h2>
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
