// The Admin area's Connections (ADR-140 Amendment 4): where the deployment's sources are read from,
// each named by an administrator and audited. Files (the ingest root) is built in; SQL, API and
// JSON-schema connections arrive with phase 9.
import { useEffect, useState } from "react";

import type { Connection } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { addConnection, listAdminConnections } from "../../ingest/sources/api";
import type { AdminApi } from "../api";

export function Connections({ api }: { api: AdminApi }) {
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [name, setName] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);

  useEffect(() => {
    listAdminConnections(api)
      .then(setConnections)
      .catch((e: Error) => setProblem(e.message));
  }, [api]);

  async function add() {
    setProblem(null);
    try {
      const made = await addConnection(api, { kind: "files", name: name.trim() });
      setConnections((all) => [...(all ?? []), made]);
      setName("");
      setSaid(`Named ${made.name}.`);
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "The connection could not be named.");
    }
  }

  return (
    <section aria-label="Connections" style={{ display: "grid", gap: "var(--sp-12)", maxWidth: 720 }}>
      <p className="label" style={{ margin: 0 }}>
        Where sources are read from. Files, the ingest root, is built in; a source is registered on a connection in
        the Ingest Studio&apos;s Sources tab. Database and API connections come later.
      </p>
      {problem && <p role="alert">{problem}</p>}
      {connections === null && !problem && <p className="label">Reading…</p>}
      {connections && (
        <table className="table" aria-label="Connections of this deployment">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Kind</th>
              <th scope="col">Named by</th>
            </tr>
          </thead>
          <tbody>
            {connections.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.kind === "files" ? "Files" : c.kind}</td>
                <td>{c.created_by === "system" ? "built in" : c.created_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "end" }}>
        <label style={{ display: "grid", gap: "var(--sp-2)" }}>
          <span className="label">New Files connection</span>
          <Input value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
        </label>
        <Button variant="primary" disabled={!name.trim()} onClick={() => void add()}>
          Name the connection
        </Button>
      </div>
      {said && <p role="status">{said}</p>}
    </section>
  );
}
