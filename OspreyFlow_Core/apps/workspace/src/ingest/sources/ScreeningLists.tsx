// Screening lists in Studio › Sources (ADR-140 Amendment 9 decision 3; Amendment 13). A list is imported
// once for the deployment through its format's template (or the blank template's column picks), and this
// dataset subscribes to it by its id: its rules and lookups read only the lists it subscribes to. Whoever
// may load screening lists also imports, refreshes and schedules them here. Below, the lists this dataset
// reads (its own and its subscriptions), and its own list's rows imported from one of its files.
import { useCallback, useEffect, useState } from "react";

import type {
  BlankListMapping,
  DatasetSubscriptions,
  DeploymentList,
  DeploymentListInput,
  ListSchedule,
  OfferedList,
} from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { Select } from "../../design/primitives/Select";
import type { IngestSourceFile } from "../api";
import {
  addDeploymentList,
  importOwnList,
  listDatasetFiles,
  listDeploymentLists,
  listSubscriptions,
  offeredLists,
  refreshDeploymentList,
  setDeploymentListSchedule,
  setSubscribed,
  type SourcesApi,
} from "./api";

type ListTemplate = DeploymentListInput["template"];

/** Each template, in words. OpenSanctions and the UN list read synthetic lists only until licensed. */
export const TEMPLATES: { value: ListTemplate; label: string }[] = [
  { value: "ofac_sdn", label: "OFAC SDN" },
  { value: "uk_sanctions_list", label: "UK Sanctions List" },
  { value: "ofsi_consolidated", label: "OFSI consolidated (closed list)" },
  { value: "un_consolidated", label: "UN consolidated (synthetic only until licensed)" },
  { value: "eu_consolidated", label: "EU consolidated" },
  { value: "opensanctions", label: "OpenSanctions (synthetic only until licensed)" },
  { value: "blank", label: "Blank: map a list's own columns" },
];

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const MAPPED: { key: keyof BlankListMapping; label: string; required?: boolean }[] = [
  { key: "ref", label: "Reference column", required: true },
  { key: "primary_name", label: "Name column", required: true },
  { key: "aliases", label: "Aliases column" },
  { key: "date_of_birth", label: "Date of birth column" },
  { key: "nationality", label: "Nationality column" },
  { key: "identifiers", label: "Identifiers column" },
  { key: "programme", label: "Programme column" },
];

export interface ScreeningListsProps {
  api: SourcesApi;
  datasetId: string;
}

function lastImport(l: DeploymentList): string {
  if (l.failure) return `Failed: ${l.failure}`;
  if (!l.updated_at) return "never imported";
  return new Date(l.updated_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export function ScreeningLists({ api, datasetId }: ScreeningListsProps) {
  const [subs, setSubs] = useState<DatasetSubscriptions | null>(null);
  const [canManage, setCanManage] = useState(false);
  const [offered, setOffered] = useState<OfferedList[] | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [scheduling, setScheduling] = useState<DeploymentList | null>(null);
  const [importingOwn, setImportingOwn] = useState(false);

  const reload = useCallback(() => {
    listSubscriptions(api, datasetId).then(setSubs).catch((e: Error) => setProblem(e.message));
    listDeploymentLists(api)
      .then((found) => setCanManage(found !== null))
      .catch(() => setCanManage(false));
    offeredLists(api, datasetId).then(setOffered).catch(() => setOffered(null));
  }, [api, datasetId]);

  useEffect(reload, [reload]);

  async function act(what: () => Promise<string>) {
    setProblem(null);
    setStatus(null);
    try {
      setStatus(await what());
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "That could not be done.");
    }
    reload();
  }

  const subscribed = new Set(subs?.subscribed ?? []);

  return (
    <section aria-label="Screening lists" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
        <h2 style={{ margin: 0, fontSize: "var(--fs-16)", flex: 1 }}>Screening lists</h2>
        {canManage && !adding && <Button onClick={() => setAdding(true)}>Import a list</Button>}
      </div>
      <p className="label" style={{ margin: 0 }}>
        Each list is imported once for the deployment. This dataset&apos;s rules and lookups read only the lists it
        subscribes to.
      </p>
      {status && <p role="status">{status}</p>}
      {problem && <p role="alert">{problem}</p>}
      {adding && (
        <ImportListForm
          onCancel={() => setAdding(false)}
          onSubmit={(body) =>
            act(async () => {
              const made = await addDeploymentList(api, body);
              setAdding(false);
              const done = await refreshDeploymentList(api, made.id);
              return done.words;
            })
          }
        />
      )}
      {scheduling && (
        <ScheduleForm
          list={scheduling}
          onCancel={() => setScheduling(null)}
          onSubmit={(schedule) =>
            act(async () => {
              const saved = await setDeploymentListSchedule(api, scheduling.id, { schedule });
              setScheduling(null);
              return saved.schedule_words ? `${saved.name}: refreshed ${saved.schedule_words}.` : `${saved.name}: refreshed by hand only.`;
            })
          }
        />
      )}
      {subs === null && !problem && <p className="label">Reading the lists…</p>}
      {subs?.lists.length === 0 && <p className="label">No screening list is imported for this deployment yet.</p>}
      {subs && subs.lists.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th scope="col">List</th>
              <th scope="col">Template</th>
              <th scope="col">Version</th>
              <th scope="col">Entries</th>
              <th scope="col">Last import</th>
              <th scope="col">Refreshed</th>
              <th scope="col">This dataset</th>
              {canManage && <th scope="col">Manage</th>}
            </tr>
          </thead>
          <tbody>
            {subs.lists.map((l) => (
              <tr key={l.id}>
                <td>{l.name}</td>
                <td>{TEMPLATES.find((t) => t.value === l.template)?.label ?? l.template}</td>
                <td>{l.version || "none yet"}</td>
                <td>{l.entries}</td>
                <td>{lastImport(l)}</td>
                <td>{l.schedule_words ?? "by hand"}</td>
                <td>
                  <label style={{ display: "flex", gap: "var(--sp-4)", alignItems: "center" }}>
                    <input
                      type="checkbox"
                      checked={subscribed.has(l.id)}
                      aria-label={`Subscribe this dataset to ${l.name}`}
                      onChange={(e) => {
                        const on = e.target.checked;
                        void act(async () => {
                          await setSubscribed(api, datasetId, l.id, on);
                          return on ? `This dataset now reads ${l.name}.` : `This dataset no longer reads ${l.name}.`;
                        });
                      }}
                    />
                    <span>{subscribed.has(l.id) ? "Subscribed" : "Not subscribed"}</span>
                  </label>
                </td>
                {canManage && (
                  <td style={{ display: "flex", gap: "var(--sp-4)" }}>
                    <Button
                      aria-label={`Refresh ${l.name} now`}
                      onClick={() => void act(async () => (await refreshDeploymentList(api, l.id)).words)}
                    >
                      Refresh now
                    </Button>
                    <Button aria-label={`Schedule ${l.name}`} onClick={() => setScheduling(l)}>
                      Schedule
                    </Button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3 style={{ margin: 0, fontSize: "var(--fs-14)" }}>Lists this dataset reads</h3>
      {offered && offered.length === 0 && <p className="label">This dataset reads no list yet.</p>}
      {offered && offered.length > 0 && (
        <ul aria-label="Lists this dataset reads" style={{ margin: 0 }}>
          {offered.map((o) => (
            <li key={o.id}>{`${o.name}, version ${o.version} (${o.deployment_wide ? "deployment-wide, subscribed" : "this dataset's own"})`}</li>
          ))}
        </ul>
      )}
      {importingOwn ? (
        <OwnListForm
          api={api}
          datasetId={datasetId}
          onCancel={() => setImportingOwn(false)}
          onSubmit={(listId, body) =>
            act(async () => {
              const done = await importOwnList(api, datasetId, listId, body);
              setImportingOwn(false);
              return done.words;
            })
          }
        />
      ) : (
        <div>
          <Button onClick={() => setImportingOwn(true)}>Import rows for one of this dataset&apos;s lists</Button>
        </div>
      )}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "grid", gap: "var(--sp-2)" }}>
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

interface ImportListFormProps {
  onSubmit: (body: { name: string; template: ListTemplate; location: string; mapping?: BlankListMapping | null }) => void;
  onCancel: () => void;
}

export function ImportListForm({ onSubmit, onCancel }: ImportListFormProps) {
  const [name, setName] = useState("");
  const [template, setTemplate] = useState<ListTemplate>("ofac_sdn");
  const [location, setLocation] = useState("");
  const [columns, setColumns] = useState<Record<string, string>>({});
  const [separator, setSeparator] = useState<"|" | ";" | ",">("|");
  const [party, setParty] = useState<"Person" | "Organisation" | "column">("Person");
  const [partyColumn, setPartyColumn] = useState("");
  const blank = template === "blank";
  const gaps = [
    !name.trim() && "a name",
    !location.trim() && "the file",
    blank && !columns.ref?.trim() && "the reference column",
    blank && !columns.primary_name?.trim() && "the name column",
    blank && party === "column" && !partyColumn.trim() && "the column that says person or organisation",
  ].filter(Boolean) as string[];

  function submit() {
    const pick = (k: string) => columns[k]?.trim() || null;
    const mapping: BlankListMapping | null = blank
      ? {
          ref: pick("ref") ?? "",
          primary_name: pick("primary_name") ?? "",
          aliases: pick("aliases"),
          date_of_birth: pick("date_of_birth"),
          nationality: pick("nationality"),
          identifiers: pick("identifiers"),
          programme: pick("programme"),
          separator,
          entity_type: party === "column" ? null : party,
          entity_type_column: party === "column" ? partyColumn.trim() : null,
          listing: "sanction",
        }
      : null;
    onSubmit({ name: name.trim(), template, location: location.trim(), mapping });
  }

  return (
    <form
      aria-label="Import a list"
      onSubmit={(e) => {
        e.preventDefault();
        if (gaps.length === 0) submit();
      }}
      style={{ display: "grid", gap: "var(--sp-8)", maxWidth: 520 }}
    >
      <Field label="List name">
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Template">
        <Select value={template} onChange={(e) => setTemplate(e.target.value as ListTemplate)}>
          {TEMPLATES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="File in the ingest folder">
        <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="lists/SDN.CSV" />
      </Field>
      {blank && (
        <fieldset style={{ display: "grid", gap: "var(--sp-8)", border: "none", padding: 0, margin: 0 }}>
          <legend className="label">The list&apos;s own columns, one for each screening field</legend>
          {MAPPED.map((m) => (
            <Field key={m.key} label={m.required ? m.label : `${m.label} (optional)`}>
              <Input value={columns[m.key] ?? ""} onChange={(e) => setColumns({ ...columns, [m.key]: e.target.value })} />
            </Field>
          ))}
          <Field label="Many values in one cell are separated by">
            <Select value={separator} onChange={(e) => setSeparator(e.target.value as "|" | ";" | ",")}>
              <option value="|">a bar ( | )</option>
              <option value=";">a semicolon ( ; )</option>
              <option value=",">a comma ( , )</option>
            </Select>
          </Field>
          <Field label="Each row is">
            <Select value={party} onChange={(e) => setParty(e.target.value as "Person" | "Organisation" | "column")}>
              <option value="Person">a person</option>
              <option value="Organisation">an organisation</option>
              <option value="column">said by a column (Person or Organisation)</option>
            </Select>
          </Field>
          {party === "column" && (
            <Field label="Party type column">
              <Input value={partyColumn} onChange={(e) => setPartyColumn(e.target.value)} />
            </Field>
          )}
        </fieldset>
      )}
      {gaps.length > 0 && <p className="label" style={{ margin: 0 }}>{`Still to give: ${gaps.join(", ")}.`}</p>}
      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={gaps.length > 0}>
          Add and import
        </Button>
      </div>
    </form>
  );
}

interface ScheduleFormProps {
  list: DeploymentList;
  onSubmit: (schedule: ListSchedule | null) => void;
  onCancel: () => void;
}

export function ScheduleForm({ list, onSubmit, onCancel }: ScheduleFormProps) {
  const [every, setEvery] = useState<"daily" | "weekly">(list.schedule?.every === "weekly" ? "weekly" : "daily");
  const [hour, setHour] = useState(list.schedule?.hour ?? 5);
  const [weekday, setWeekday] = useState(list.schedule?.weekday ?? 1);
  return (
    <form
      aria-label={`Schedule ${list.name}`}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ every, hour, weekday: every === "weekly" ? weekday : null });
      }}
      style={{ display: "grid", gap: "var(--sp-8)", maxWidth: 520 }}
    >
      <Field label="Refresh">
        <Select value={every} onChange={(e) => setEvery(e.target.value as "daily" | "weekly")}>
          <option value="daily">every day</option>
          <option value="weekly">every week</option>
        </Select>
      </Field>
      {every === "weekly" && (
        <Field label="On">
          <Select value={String(weekday)} onChange={(e) => setWeekday(Number(e.target.value))}>
            {WEEKDAYS.map((d, i) => (
              <option key={d} value={i + 1}>
                {d}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <Field label="At (UK time)">
        <Select value={String(hour)} onChange={(e) => setHour(Number(e.target.value))}>
          {Array.from({ length: 24 }, (_, h) => (
            <option key={h} value={h}>{`${String(h).padStart(2, "0")}:00`}</option>
          ))}
        </Select>
      </Field>
      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="button" onClick={() => onSubmit(null)}>
          Refresh by hand only
        </Button>
        <Button type="submit" variant="primary">
          Save schedule
        </Button>
      </div>
    </form>
  );
}

interface OwnListFormProps {
  api: SourcesApi;
  datasetId: string;
  onSubmit: (listId: string, body: { location: string; name?: string | null; key_column?: string | null }) => void;
  onCancel: () => void;
}

function OwnListForm({ api, datasetId, onSubmit, onCancel }: OwnListFormProps) {
  const [files, setFiles] = useState<IngestSourceFile[] | null>(null);
  const [listId, setListId] = useState("");
  const [location, setLocation] = useState("");
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  useEffect(() => {
    listDatasetFiles(api, datasetId)
      .then((l) => setFiles(l.files))
      .catch(() => setFiles([]));
  }, [api, datasetId]);
  const gaps = [!listId.trim() && "the list's id", !location && "the file"].filter(Boolean) as string[];
  return (
    <form
      aria-label="Import rows for one of this dataset's lists"
      onSubmit={(e) => {
        e.preventDefault();
        if (gaps.length === 0) onSubmit(listId.trim(), { location, name: name.trim() || null, key_column: key.trim() || null });
      }}
      style={{ display: "grid", gap: "var(--sp-8)", maxWidth: 520 }}
    >
      <Field label="The list's id, as the domain model names it">
        <Input value={listId} onChange={(e) => setListId(e.target.value)} />
      </Field>
      <Field label="File">
        <Select value={location} onChange={(e) => setLocation(e.target.value)}>
          <option value="">Choose a file</option>
          {(files ?? []).map((f) => (
            <option key={f.source_location} value={f.source_location}>
              {f.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="List name (its first import only)">
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Key column (its first import only)">
        <Input value={key} onChange={(e) => setKey(e.target.value)} />
      </Field>
      {gaps.length > 0 && <p className="label" style={{ margin: 0 }}>{`Still to give: ${gaps.join(", ")}.`}</p>}
      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={gaps.length > 0}>
          Import rows
        </Button>
      </div>
    </form>
  );
}
