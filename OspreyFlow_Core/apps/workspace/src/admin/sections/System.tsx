// Admin › Running › System (ADR-110 Amendment 1, ADR-135, ADR-136, ADR-114 decision 13; ADR-145
// decision 5 and Amendment 4 decision 7): each component asked as the section opens, the models and
// engines, the version, and *Dataset owners may be*. Behind `administer_system`.
import { useEffect, useState } from "react";

import type {
  ConvertedViews,
  DatasetOwnerSetting,
  EngineStatus,
  SystemStatus,
  UpdateNotice,
} from "../../../../../packages/schemas/generated";
import { Button, Select } from "../../design/primitives";
import { datasetOwnerSetting, setDatasetOwnerSetting, systemStatus, type AdminApi } from "../api";
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
      {status?.converted_views && <ConvertedSection converted={status.converted_views} />}
      <Button onClick={ask}>Ask again</Button>
      <OwnersMayBe api={api} />
    </>
  );
}

type OwnersMayBeValue = NonNullable<DatasetOwnerSetting["owners_may_be"]>;

const OWNERS_MAY_BE: { value: OwnersMayBeValue; label: string }[] = [
  { value: "people_and_teams", label: "People and teams" },
  { value: "people_only", label: "People only" },
  { value: "teams_only", label: "Teams only" },
];

/** ADR-145 Amendment 4 decision 7: who may be named a dataset's owner, at *Make live* and in Admin ›
 * Datasets' *Change owner…*. Saved by its own button; the Conduit audits it. */
function OwnersMayBe({ api }: { api: AdminApi }) {
  const [held, setHeld] = useState<OwnersMayBeValue | null>(null);
  const [chosen, setChosen] = useState<OwnersMayBeValue>("people_and_teams");
  const [said, setSaid] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    datasetOwnerSetting(api)
      .then((found) => {
        const value = found.owners_may_be ?? "people_and_teams";
        setHeld(value);
        setChosen(value);
      })
      .catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);
  const save = () => {
    setSaid(null);
    setProblem(null);
    void setDatasetOwnerSetting(api, chosen)
      .then((saved) => {
        const value = saved.owners_may_be ?? "people_and_teams";
        setHeld(value);
        setSaid(`Dataset owners may now be: ${OWNERS_MAY_BE.find((o) => o.value === value)?.label.toLowerCase()}.`);
      })
      .catch((e: Error) => setProblem(e.message));
  };
  return (
    <section aria-label="Dataset owners" style={{ display: "grid", gap: "var(--sp-6)" }}>
      <h4 style={{ margin: 0 }}>Dataset owners</h4>
      <p className="label" style={{ margin: 0 }}>
        Who may be named to answer for a dataset, at its first Make live and in Admin › Datasets&apos; Change owner. Choose
        teams only if no person&apos;s name should be shown as an owner. Teams arrive with teams themselves: until then a
        dataset&apos;s owners are people, and teams only refuses every owner.
      </p>
      {held && (
        <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
          <Select aria-label="Dataset owners may be" value={chosen} onChange={(e) => setChosen(e.target.value as OwnersMayBeValue)}>
            {OWNERS_MAY_BE.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <Button aria-label="Save who dataset owners may be" onClick={save}>
            Save
          </Button>
        </div>
      )}
      {problem && <p role="alert">{problem}</p>}
      {said && <p role="status">{said}</p>}
    </section>
  );
}

/** Each model engine (ADR-135 decision 5): its models per role, the roles it is the default for,
 * whether its key is present — Yes or No — and (ADR-136 decision 1) whether it is under a privacy
 * contract, with the agreement's reference. Only the named fields are read, so nothing else the
 * response might carry, a key least of all, reaches the page. A summary: since ADR-135 Amendment 2
 * engines, defaults and keys are changed in Admin › Models or with `ospreyflow models`, never here. */
function EnginesTable({ engines }: { engines: EngineStatus[] }) {
  return (
    <>
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
    <p className="label" style={{ margin: 0 }}>
      Engines, each job&apos;s default and their keys are changed in Admin › Models, or with ospreyflow models on
      the deployment&apos;s host.
    </p>
    </>
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

const many = (n: number, one: string, more: string) => `${n} ${n === 1 ? one : more}`;

/** ADR-144 decision 6: what the conversion to views made of the cases made from another, counted
 * by the Conduit in this administrator's own unit only. */
export function convertedWords(c: ConvertedViews): string[] {
  if (c.problem) return [c.problem, "The conversion's dry-run report, which the operator runs, names each case it did not place."];
  const views = c.views ?? 0;
  const cases = c.cases ?? 0;
  return [
    views
      ? `${many(views, "case made from another", "cases made from another")} became ${views === 1 ? "a view" : "views"}, in ${many(cases, "case", "cases")} of your unit.`
      : "No case made from another has become a view in your unit.",
    "Any the conversion could not place stays as it was: its dry-run report, which the operator runs, names each and why.",
  ];
}

function ConvertedSection({ converted }: { converted: ConvertedViews }) {
  const [made, waiting] = convertedWords(converted);
  return (
    <section aria-label="Cases converted to views" style={{ display: "grid", gap: "var(--sp-6)" }}>
      <p className="value" style={{ margin: 0 }}>{made}</p>
      <p className="label" style={{ margin: 0 }}>{waiting}</p>
    </section>
  );
}
