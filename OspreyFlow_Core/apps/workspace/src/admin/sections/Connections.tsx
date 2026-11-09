// The Admin area's Connections (ADR-140 Amendments 4, 13 and 15; L2.7): where the deployment's sources
// are read from, each named by an administrator and audited. Files (the ingest root) is built in; a
// SQL database, an HTTP API or JSON files are named here with their own settings and the datasets
// whose sources may read through them. **A connection names its secret, never its value**: the value
// is set by the operator in `deployment.env` (`OSPREY_CONNECTION_SECRET_<NAME>`), and no field here
// takes it, so none is ever sent or answered. A secret's field that holds anything other than a name
// is refused here before it is sent, and the Conduit refuses it again without answering it back
// (`test_admin_connection_fields.py`). Which hosts may be reached is the operator's, not Admin's
// (`connectors.private_hosts`, the egress allow-list), so this screen only says so.
import { useEffect, useMemo, useState } from "react";

import type { AdminDataset, Connection, ConnectionInput } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { Select } from "../../design/primitives/Select";
import { addConnection, listAdminConnections } from "../../ingest/sources/api";
import { listDatasets, testConnection, type AdminApi } from "../api";

type Kind = "files" | "sql" | "api" | "json";

const KINDS: { id: Kind; label: string }[] = [
  { id: "files", label: "Files" },
  { id: "sql", label: "SQL database" },
  { id: "api", label: "HTTP API" },
  { id: "json", label: "JSON files" },
];
const KIND_WORDS: Record<string, string> = Object.fromEntries(KINDS.map((k) => [k.id, k.label]));

/** The shape a secret's name takes (`schemas/sources.py`'s `SECRET_NAME`): capitals, digits and `_`. */
export const SECRET_NAME = /^[A-Z][A-Z0-9_]{0,63}$/;

export const SECRET_TIP =
  "The name of a secret your operator sets in deployment.env as OSPREY_CONNECTION_SECRET_<NAME>. Type the name only, never the password or token itself: the value never passes through Admin, and each secret belongs to one connection.";
export const REACH_TIP =
  "A host inside your network is reached only if your operator admits it in osprey.yaml (connectors.private_hosts); an API's host must also be on the operator's egress allow-list.";

interface Fields {
  host: string;
  port: string;
  database: string;
  user: string;
  secret: string;
  tls: "verify-full" | "require";
  schemas: string;
  ca: string;
  baseUrl: string;
  auth: "none" | "bearer";
  pagination: "none" | "page" | "next_link";
  pageParam: string;
  nextAt: string;
}

const EMPTY: Fields = {
  host: "", port: "5432", database: "", user: "", secret: "", tls: "verify-full", schemas: "public", ca: "",
  baseUrl: "https://", auth: "none", pagination: "none", pageParam: "page", nextAt: "",
}; // prettier-ignore

/** What the form sends: the kind's own settings, the secret by name, and nothing a secret's value
 * could be in. */
export function connectionBody(kind: Kind, name: string, datasets: string[], f: Fields): ConnectionInput {
  const ca = f.ca.trim() ? { ca_certificate: f.ca.trim() } : {};
  if (kind === "files") return { kind, name: name.trim() } as ConnectionInput;
  if (kind === "json") return { kind, name: name.trim(), datasets, settings: { kind } } as ConnectionInput;
  if (kind === "sql") {
    return {
      kind, name: name.trim(), datasets,
      settings: {
        kind, host: f.host.trim(), port: Number(f.port), database: f.database.trim(), user: f.user.trim(),
        secret: f.secret.trim(), tls: f.tls, ...ca,
        schemas: f.schemas.split(",").map((s) => s.trim()).filter(Boolean),
      },
    } as ConnectionInput; // prettier-ignore
  }
  return {
    kind, name: name.trim(), datasets,
    settings: {
      kind, base_url: f.baseUrl.trim(), auth: f.auth, ...(f.auth === "bearer" ? { secret: f.secret.trim() } : {}),
      pagination: f.pagination, ...(f.pagination === "page" ? { page_param: f.pageParam.trim() } : {}),
      ...(f.pagination === "next_link" ? { next_at: f.nextAt.trim() } : {}), ...ca,
    },
  } as ConnectionInput; // prettier-ignore
}

/** Why the form cannot be sent yet, or `null`. A secret's field holding anything but a name is never
 * sent: it may be the value itself. */
export function notYet(kind: Kind, name: string, datasets: string[], f: Fields): string | null {
  if (!name.trim()) return "Give the connection a name.";
  if (kind === "files") return null;
  if (datasets.length === 0) return "Choose the datasets whose sources may read through it.";
  const needsSecret = kind === "sql" || (kind === "api" && f.auth === "bearer");
  if (needsSecret && !SECRET_NAME.test(f.secret.trim()))
    return "The secret's field takes its name in capitals (such as TELCO_API), never the password or token itself.";
  if (kind === "sql" && (!f.host.trim() || !f.database.trim() || !f.user.trim())) return "Give the host, the database and the login.";
  if (kind === "api" && !/^https:\/\/[^\s/]+/.test(f.baseUrl.trim())) return "The base URL starts https:// and names its host.";
  return null;
}

function where(c: Connection): string {
  const s = c.settings as { kind?: string; host?: string; port?: number; database?: string; base_url?: string } | null | undefined;
  if (!s) return c.kind === "files" ? "the ingest root" : "";
  if (s.kind === "sql") return `${s.host}:${s.port}/${s.database}`;
  if (s.kind === "api") return s.base_url ?? "";
  return "JSON files in the ingest root";
}

function secretOf(c: Connection): string {
  const s = c.settings as { secret?: string | null } | null | undefined;
  return s?.secret ? s.secret : "none";
}

export function Connections({ api }: { api: AdminApi }) {
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [datasets, setDatasets] = useState<AdminDataset[]>([]);
  const [kind, setKind] = useState<Kind>("files");
  const [name, setName] = useState("");
  const [bound, setBound] = useState<string[]>([]);
  const [fields, setFields] = useState<Fields>(EMPTY);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [tested, setTested] = useState<Record<string, { ok: boolean; words: string }>>({});

  useEffect(() => {
    listAdminConnections(api)
      .then(setConnections)
      .catch((e: Error) => setProblem(e.message));
    listDatasets(api)
      .then((all) => setDatasets(all.filter((d) => d.kind !== "composite")))
      .catch(() => setDatasets([]));
  }, [api]);

  const names = useMemo(() => new Map(datasets.map((d) => [d.id, d.name])), [datasets]);
  const set = <K extends keyof Fields>(key: K, value: Fields[K]) => setFields((f) => ({ ...f, [key]: value }));
  const blocked = notYet(kind, name, bound, fields);

  async function add() {
    setProblem(null);
    setSaid(null);
    if (blocked) return setProblem(blocked);
    try {
      const made = await addConnection(api, connectionBody(kind, name, bound, fields));
      setConnections((all) => [...(all ?? []), made]);
      setName("");
      setBound([]);
      setFields(EMPTY);
      setSaid(`Named ${made.name}.`);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "The connection could not be named.");
    }
  }

  async function test(c: Connection) {
    try {
      const result = await testConnection(api, c.id);
      setTested((t) => ({ ...t, [c.id]: result }));
    } catch (e) {
      setTested((t) => ({ ...t, [c.id]: { ok: false, words: e instanceof Error ? e.message : "Not tested." } }));
    }
  }

  const field = (label: string, key: keyof Fields, props: { tip?: string; tipId?: string; inputMode?: "numeric" } = {}) => (
    <div style={{ display: "grid", gap: "var(--sp-2)" }}>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">{label}</span>
        <Input
          value={fields[key] as string}
          onChange={(e) => set(key, e.target.value as never)}
          aria-describedby={props.tipId}
          inputMode={props.inputMode}
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      {props.tip && props.tipId && (
        <span id={props.tipId} className="caption">
          {props.tip}
        </span>
      )}
    </div>
  );

  return (
    <section aria-label="Connections" style={{ display: "grid", gap: "var(--sp-12)", maxWidth: 760 }}>
      <p className="label" style={{ margin: 0 }}>
        Where sources are read from. Files, the ingest root, is built in. A SQL database, an HTTP API or JSON files are named
        here with the datasets whose sources may read through them; a source is registered on a connection in the Ingest
        Studio&apos;s Sources tab.
      </p>
      {problem && <p role="alert">{problem}</p>}
      {connections === null && !problem && <p className="label">Reading…</p>}
      {connections && (
        <table className="table" aria-label="Connections of this deployment">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Kind</th>
              <th scope="col">Reads</th>
              <th scope="col">Secret&apos;s name</th>
              <th scope="col">Datasets</th>
              <th scope="col">Named by</th>
              <th scope="col">
                <span className="visually-hidden">Test</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {connections.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{KIND_WORDS[c.kind] ?? c.kind}</td>
                <td>{where(c)}</td>
                <td>{c.kind === "files" || c.kind === "json" ? "—" : secretOf(c)}</td>
                <td>{(c.datasets ?? []).map((d) => names.get(d) ?? d).join(", ") || "—"}</td>
                <td>{c.created_by === "system" ? "built in" : c.created_by}</td>
                <td>
                  {c.kind !== "files" && (
                    <>
                      <Button onClick={() => void test(c)} aria-label={`Test ${c.name}`}>
                        Test connection
                      </Button>
                      {tested[c.id] && (
                        <span role="status" className="caption" style={{ display: "block" }}>
                          {tested[c.id]!.ok ? "✓ " : "✗ "}
                          {tested[c.id]!.words}
                        </span>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <fieldset style={{ display: "grid", gap: "var(--sp-8)", border: "1px solid var(--border-subtle)", padding: "var(--sp-12)" }}>
        <legend className="label">Name a connection</legend>
        <label style={{ display: "grid", gap: "var(--sp-2)" }}>
          <span className="label">Kind</span>
          <Select value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
            {KINDS.map((k) => (
              <option key={k.id} value={k.id}>
                {k.label}
              </option>
            ))}
          </Select>
        </label>
        <label style={{ display: "grid", gap: "var(--sp-2)" }}>
          <span className="label">Connection name</span>
          <Input value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
        </label>
        {kind !== "files" && (
          <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: "var(--sp-4)" }}>
            <legend className="label">Datasets whose sources may read through it</legend>
            {datasets.length === 0 && <span className="caption">No dataset to bind it to yet.</span>}
            {datasets.map((d) => (
              <label key={d.id} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={bound.includes(d.id)}
                  onChange={(e) => setBound((b) => (e.target.checked ? [...b, d.id] : b.filter((x) => x !== d.id)))}
                />
                {d.name}
              </label>
            ))}
          </fieldset>
        )}
        {kind === "sql" && (
          <>
            {field("Host", "host", { tip: REACH_TIP, tipId: "connection-reach-tip" })}
            {field("Port", "port", { inputMode: "numeric" })}
            {field("Database", "database")}
            {field("Read-only login", "user")}
            {field("Secret's name (the login's password)", "secret", { tip: SECRET_TIP, tipId: "connection-secret-tip" })}
            <label style={{ display: "grid", gap: "var(--sp-2)" }}>
              <span className="label">TLS</span>
              <Select value={fields.tls} onChange={(e) => set("tls", e.target.value as Fields["tls"])}>
                <option value="verify-full">Verify the server&apos;s certificate and name</option>
                <option value="require">Encrypt only, without checking the server</option>
              </Select>
            </label>
            {field("Schemas a source may read (comma-separated)", "schemas")}
          </>
        )}
        {kind === "api" && (
          <>
            {field("Base URL", "baseUrl", { tip: REACH_TIP, tipId: "connection-reach-tip" })}
            <label style={{ display: "grid", gap: "var(--sp-2)" }}>
              <span className="label">Sign-in</span>
              <Select value={fields.auth} onChange={(e) => set("auth", e.target.value as Fields["auth"])}>
                <option value="none">None</option>
                <option value="bearer">A bearer token, by its secret&apos;s name</option>
              </Select>
            </label>
            {fields.auth === "bearer" && field("Secret's name (the token)", "secret", { tip: SECRET_TIP, tipId: "connection-secret-tip" })}
            <label style={{ display: "grid", gap: "var(--sp-2)" }}>
              <span className="label">Paging</span>
              <Select value={fields.pagination} onChange={(e) => set("pagination", e.target.value as Fields["pagination"])}>
                <option value="none">One page</option>
                <option value="page">Numbered pages, until one is empty</option>
                <option value="next_link">Each page names the next</option>
              </Select>
            </label>
            {fields.pagination === "page" && field("Page parameter", "pageParam")}
            {fields.pagination === "next_link" && field("Where the next page's link is (a dotted path)", "nextAt")}
          </>
        )}
        {(kind === "sql" || kind === "api") && (
          <label style={{ display: "grid", gap: "var(--sp-2)" }}>
            <span className="label">Your own certificate authority (optional, PEM)</span>
            <textarea className="input" rows={3} value={fields.ca} spellCheck={false} onChange={(e) => set("ca", e.target.value)} />
          </label>
        )}
        <div>
          <Button variant="primary" onClick={() => void add()}>
            Name the connection
          </Button>
        </div>
      </fieldset>
      {said && <p role="status">{said}</p>}
    </section>
  );
}
