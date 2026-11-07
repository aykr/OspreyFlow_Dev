// Admin › Running › System (ADR-110 Amendment 1, ADR-135, ADR-136, ADR-114 decision 13; ADR-145
// decision 5): each component asked as the section opens, the models and engines, the version.
// Behind `administer_system`.
import { useEffect, useState } from "react";

import type { EngineStatus, SystemStatus, UpdateNotice } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives";
import { systemStatus, type AdminApi } from "../api";
import { updateWords } from "../updateNotice";

export function System({ api }: { api: AdminApi }) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const ask = () => {
    setProblem(null);
    systemStatus(api).then(setStatus).catch((e: Error) => setProblem(e.message));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(ask, [api.apiBaseUrl, api.bearerToken]);
  return (
    <>
      {problem && <p role="alert">{problem}</p>}
      {status && (
        <ul aria-label="Components" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-8)" }}>
          {(status.components ?? []).map((c) => (
            <li key={c.name} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "baseline" }}>
              <span aria-hidden style={{ width: 10, height: 10, borderRadius: "50%", background: `var(${c.ok ? "--success" : "--error"})` }} />
              <span className="value">{c.name}</span>
              {/* ADR-114 Amendment 36: a part that answered and is wrong says what to do, not "not answering". */}
              <span className="label">
                {c.ok ? `answered in ${c.millis} ms` : (c.notice ?? `not answering: ${c.detail ?? "no reason given"}`)}
              </span>
            </li>
          ))}
        </ul>
      )}
      {status?.model_notice && (
        <p role="note" style={{ margin: 0, border: "1px solid var(--warning)", padding: "var(--sp-8)" }}>
          {status.model_notice}
        </p>
      )}
      {status?.models && status.models.length > 0 && (
        <table className="table" aria-label="Models">
          <thead>
            <tr>
              <th>Role</th>
              <th>Model</th>
              <th>Runs at</th>
            </tr>
          </thead>
          <tbody>
            {status.models.map((m) => (
              <tr key={m.role}>
                <td>{m.role}</td>
                <td>
                  <code>{m.model}</code>
                  {m.runs_at !== "this deployment" && m.local_model && (
                    <div className="label">{`Anything that may not be sent runs on ${m.local_model}.`}</div>
                  )}
                </td>
                <td>{m.runs_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {status?.engines && status.engines.length > 0 && <EnginesTable engines={status.engines} />}
      {status && <VersionSection version={status.version} update={status.update} />}
      <Button onClick={ask}>Ask again</Button>
    </>
  );
}

/** Each model engine (ADR-135 decision 5): its models per role, the roles it is the default for,
 * whether its key is present — Yes or No — and (ADR-136 decision 1) whether it is under a privacy
 * contract, with the agreement's reference. Only the named fields are read, so nothing else the
 * response might carry, a key least of all, reaches the page. Keys are set on the host with
 * `ospreyflow models key`, and the mark in `osprey.yaml`, never here. */
function EnginesTable({ engines }: { engines: EngineStatus[] }) {
  return (
    <table className="table" aria-label="Engines">
      <thead>
        <tr>
          <th>Engine</th>
          <th>Models</th>
          <th>Default for</th>
          <th>Key present</th>
          <th>Privacy contract</th>
        </tr>
      </thead>
      <tbody>
        {engines.map((engine) => (
          <tr key={engine.name}>
            <td>{engine.label}</td>
            <td>
              {Object.entries(engine.models)
                .map(([role, model]) => `${role}: ${model}`)
                .join("; ")}
            </td>
            <td>{engine.default_for.length > 0 ? engine.default_for.join(", ") : "None"}</td>
            <td>{engine.key_present ? "Yes" : "No"}</td>
            <td>{contractWords(engine)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function contractWords(engine: EngineStatus): string {
  if (engine.name === "local") return "Not needed: nothing leaves";
  if (!engine.privacy_contract) return "No contract";
  return engine.contract_reference ? `Under contract (${engine.contract_reference})` : "Under contract";
}

/** The version and the last update check (ADR-114 decision 13, Amendment 8 point 2). */
function VersionSection({ version, update }: { version?: string | null; update?: UpdateNotice | null }) {
  const words = updateWords(version, update);
  return (
    <section aria-label="Version" style={{ display: "grid", gap: "var(--sp-6)" }}>
      {version && <p className="value" style={{ margin: 0 }}>{`OspreyFlow ${version}`}</p>}
      <p
        role={words.tone === "problem" ? "alert" : "status"}
        style={{
          margin: 0,
          ...(words.tone === "available" ? { border: "1px solid var(--border-strong)", padding: "var(--sp-8)" } : {}),
        }}
      >
        {words.headline}
      </p>
      <p className="label" style={{ margin: 0 }}>
        {words.detail}
      </p>
      {update?.update_available && update.url && (
        <p style={{ margin: 0 }}>
          <a href={update.url} target="_blank" rel="noreferrer">{`The ${update.latest} release`}</a>
        </p>
      )}
      {update?.update_available && update.notes && (
        <details>
          <summary>{`What is new in ${update.latest}`}</summary>
          <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{update.notes}</pre>
        </details>
      )}
    </section>
  );
}
