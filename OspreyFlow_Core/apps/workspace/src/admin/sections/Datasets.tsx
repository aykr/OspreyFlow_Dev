// Admin › Data › Datasets (ADR-136 decision 2; ADR-145 decisions 5 and 8, Amendment 4 decisions 3 and
// 6; ADR-143 Amendment 2 decisions 1 and 2): every dataset, its kind, unit, highest marking, egress and
// promotion policy; its Authors and *Change owner…*; every linked case with its layer as counts, and a
// removed case's *Merge into the dataset* and *Delete*, each run dry. Never a layer's contents: the
// Conduit sends counts only. Behind `administer_system`.
import { useEffect, useState } from "react";

import type {
  AdminDataset,
  AdminDatasetAuthors,
  AdminLinkedCase,
  LayerDryRun,
} from "../../../../../packages/schemas/generated";
import { Button, Input, Select } from "../../design/primitives";
import { AUTHORS_TIP_ID, TIPS } from "../tips";
import {
  changeDatasetOwners,
  datasetAuthors,
  datasetCases,
  deleteRemovedLayer,
  layerDryRun,
  listDatasets,
  setDatasetEgress,
  setPromotionPolicy,
  type AdminApi,
} from "../api";

const EGRESS: { value: AdminDataset["egress"]; label: string }[] = [
  { value: "none", label: "none — never sent to a hosted engine" },
  { value: "contracted", label: "contracted — only to a provider under a privacy contract" },
  { value: "any", label: "any — to any enabled provider" },
];

const KIND: Record<NonNullable<AdminDataset["kind"]>, string> = {
  source: "Source",
  composite: "Composite",
  drawn: "Drawn",
};

const POLICY: { value: NonNullable<AdminDataset["promotion_policy"]>; label: string }[] = [
  { value: "author_promotes", label: "Author promotes" },
  { value: "second_person_reviews", label: "Second person reviews" },
];

/** A layer's size as the screen says it: bytes, kB or MB (the owner's ruling of 8 November 2026). */
export function sizeWords(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** ADR-136 decision 2 and ADR-145 decision 8: every dataset, and where its material may go when a
 * model is asked. A change is one dataset at a time, saved by its own button, and the Conduit
 * audits it. *Details for …* opens a dataset's policy, Authors and linked cases. */
export function Datasets({ api }: { api: AdminApi }) {
  const [datasets, setDatasets] = useState<AdminDataset[] | null>(null);
  const [chosen, setChosen] = useState<Record<string, AdminDataset["egress"]>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    listDatasets(api).then(setDatasets).catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);
  const changed = (dataset: AdminDataset) =>
    setDatasets((current) => (current ?? []).map((d) => (d.id === dataset.id ? dataset : d)));
  const save = (dataset: AdminDataset) => {
    const egress = chosen[dataset.id] ?? dataset.egress;
    setProblem(null);
    setSaid(null);
    void setDatasetEgress(api, dataset.id, egress)
      .then((saved) => {
        changed(saved);
        setSaid(`${saved.name}: egress is now ${saved.egress}.`);
      })
      .catch((e: Error) => setProblem(e.message));
  };
  const shown = datasets?.find((d) => d.id === open) ?? null;
  return (
    <>
      <p className="label" style={{ margin: 0 }}>
        Where each dataset&apos;s material may go when a model is asked. <strong>none</strong>: never to a hosted engine.{" "}
        <strong>contracted</strong>: only to a provider marked as under a privacy contract. <strong>any</strong>: to any
        enabled provider. Every dataset is none until you change it. Its handling code must still be one the deployment
        sends, and each change is recorded in the audit log.
      </p>
      {problem && <p role="alert">{problem}</p>}
      {said && <p role="status">{said}</p>}
      {!datasets && !problem && <p className="label">Reading the datasets…</p>}
      {datasets && datasets.length > 0 && (
        <table className="table" aria-label="Datasets">
          <thead>
            <tr>
              <th>Dataset</th>
              <th>Kind</th>
              <th>Unit</th>
              <th>Highest marking it may hold</th>
              <th>Egress</th>
              <th />
              <th />
            </tr>
          </thead>
          <tbody>
            {datasets.map((dataset) => (
              <tr key={dataset.id}>
                <td>{dataset.name}</td>
                <td>{KIND[dataset.kind ?? "source"]}</td>
                <td>{dataset.owning_unit}</td>
                <td>{dataset.highest_marking ?? "The deployment's highest"}</td>
                <td>
                  <Select
                    aria-label={`Egress for ${dataset.name}`}
                    value={chosen[dataset.id] ?? dataset.egress}
                    onChange={(e) => setChosen({ ...chosen, [dataset.id]: e.target.value as AdminDataset["egress"] })}
                  >
                    {EGRESS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </td>
                <td>
                  <Button aria-label={`Save egress for ${dataset.name}`} onClick={() => save(dataset)}>
                    Save
                  </Button>
                </td>
                <td>
                  <Button
                    aria-label={`Details for ${dataset.name}`}
                    aria-expanded={open === dataset.id}
                    onClick={() => setOpen(open === dataset.id ? null : dataset.id)}
                  >
                    Details
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {datasets?.length === 0 && <p className="label" style={{ margin: 0 }}>There is no dataset yet.</p>}
      {shown && <DatasetDetails key={shown.id} api={api} dataset={shown} onChanged={changed} />}
    </>
  );
}

function DatasetDetails({
  api,
  dataset,
  onChanged,
}: {
  api: AdminApi;
  dataset: AdminDataset;
  onChanged: (dataset: AdminDataset) => void;
}) {
  const [authors, setAuthors] = useState<AdminDatasetAuthors | null>(null);
  const [cases, setCases] = useState<AdminLinkedCase[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    datasetAuthors(api, dataset.id).then(setAuthors).catch((e: Error) => setProblem(e.message));
    datasetCases(api, dataset.id)
      .then((found) => setCases(found.cases))
      .catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset.id]);
  return (
    <section aria-label={`Details of ${dataset.name}`} style={{ display: "grid", gap: "var(--sp-12)" }}>
      <h4 style={{ margin: 0 }}>{dataset.name}</h4>
      {problem && <p role="alert">{problem}</p>}
      {dataset.kind === "composite" ? (
        <p className="label" style={{ margin: 0 }}>
          A composite holds none of its members&apos; data, so nothing is promoted into it: each member has its own
          promotion policy.
        </p>
      ) : (
        <PromotionPolicy api={api} dataset={dataset} authors={authors} onChanged={onChanged} />
      )}
      {authors && <Authors api={api} dataset={dataset} authors={authors} onChanged={setAuthors} />}
      {cases && (
        <LinkedCases
          api={api}
          dataset={dataset}
          cases={cases}
          onChanged={() =>
            void datasetCases(api, dataset.id)
              .then((found) => setCases(found.cases))
              .catch((e: Error) => setProblem(e.message))
          }
        />
      )}
    </section>
  );
}

/** ADR-145 decision 8: *Author promotes* or *Second person reviews*, with who may approve (the
 * dataset's Authors holding Review promotions) and a warning when fewer than two can. */
function PromotionPolicy({
  api,
  dataset,
  authors,
  onChanged,
}: {
  api: AdminApi;
  dataset: AdminDataset;
  authors: AdminDatasetAuthors | null;
  onChanged: (dataset: AdminDataset) => void;
}) {
  const held = dataset.promotion_policy ?? "author_promotes";
  const [chosen, setChosen] = useState(held);
  const [said, setSaid] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const approvers = (authors?.people ?? []).filter((p) => p.approves);
  const save = () => {
    setSaid(null);
    setProblem(null);
    void setPromotionPolicy(api, dataset.id, chosen)
      .then((saved) => {
        onChanged(saved);
        setSaid(`${saved.name}: ${POLICY.find((p) => p.value === saved.promotion_policy)?.label}.`);
      })
      .catch((e: Error) => setProblem(e.message));
  };
  return (
    <div style={{ display: "grid", gap: "var(--sp-6)" }}>
      <h5 style={{ margin: 0 }}>Promotion of drawn items</h5>
      <p className="label" style={{ margin: 0 }}>
        How an analyst&apos;s drawn item becomes part of this dataset. <strong>Author promotes</strong>: the analyst&apos;s own
        promotion is enough. <strong>Second person reviews</strong>: one of the dataset&apos;s Authors who holds Review
        promotions approves it first, never the analyst who drew it.
      </p>
      <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
        <Select
          aria-label={`Promotion policy for ${dataset.name}`}
          value={chosen}
          onChange={(e) => setChosen(e.target.value as typeof chosen)}
        >
          {POLICY.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <Button aria-label={`Save promotion policy for ${dataset.name}`} onClick={save}>
          Save
        </Button>
      </div>
      {authors && (
        <p className="label" style={{ margin: 0 }}>
          {approvers.length === 0
            ? "No one can approve a promotion: none of its Authors holds Review promotions."
            : `Can approve: ${approvers.map((p) => p.name ?? p.id).join(", ")}.`}
        </p>
      )}
      {authors && held === "second_person_reviews" && approvers.length < 2 && (
        <p role="note" style={{ margin: 0, border: "1px solid var(--warning)", padding: "var(--sp-8)" }}>
          {`Fewer than two people can approve a promotion into ${dataset.name}: one absence stops every promotion.`}
        </p>
      )}
      {problem && <p role="alert">{problem}</p>}
      {said && <p role="status">{said}</p>}
    </div>
  );
}

/** ADR-145 Amendment 4 decisions 3 and 6: the dataset's Authors, its home case's Authors, and
 * *Change owner…*, which the Conduit holds to the same refusals as *Make live*. */
function Authors({
  api,
  dataset,
  authors,
  onChanged,
}: {
  api: AdminApi;
  dataset: AdminDataset;
  authors: AdminDatasetAuthors;
  onChanged: (authors: AdminDatasetAuthors) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [people, setPeople] = useState("");
  const [said, setSaid] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const begin = () => {
    setPeople((authors.people ?? []).map((p) => p.id).join(", "));
    setSaid(null);
    setProblem(null);
    setEditing(true);
  };
  const save = () => {
    const named = people
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean);
    setProblem(null);
    void changeDatasetOwners(api, dataset.id, named)
      .then((saved) => {
        onChanged(saved);
        setEditing(false);
        setSaid(`${dataset.name}'s Authors are now ${(saved.people ?? []).map((p) => p.name ?? p.id).join(", ")}.`);
      })
      .catch((e: Error) => setProblem(e.message));
  };
  return (
    <div style={{ display: "grid", gap: "var(--sp-6)" }}>
      <h5 style={{ margin: 0 }}>Authors</h5>
      <p id={`${AUTHORS_TIP_ID}-${dataset.id}`} className="label" style={{ margin: 0 }}>
        {TIPS.authors}
      </p>
      {!authors.has_home_case ? (
        <p style={{ margin: 0 }}>Not live yet: who answers for it is asked at its first Make live.</p>
      ) : (
        <>
          <ul aria-label={`Authors of ${dataset.name}`} style={{ margin: 0 }}>
            {(authors.people ?? []).map((p) => (
              <li key={p.id}>
                {p.name ? `${p.name} (${p.id})` : p.id}
                {p.approves ? " · can approve promotions" : ""}
              </li>
            ))}
          </ul>
          {!editing && (
            <div>
              <Button aria-label={`Change owner of ${dataset.name}`} aria-describedby={`${AUTHORS_TIP_ID}-${dataset.id}`} onClick={begin}>
                Change owner…
              </Button>
            </div>
          )}
        </>
      )}
      {editing && (
        <fieldset aria-label={`Change owner of ${dataset.name}`} style={{ display: "grid", gap: "var(--sp-6)", margin: 0 }}>
          <legend>{`Who answers for ${dataset.name}?`}</legend>
          <label style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span>{`New owners of ${dataset.name}: people's account ids, separated by commas`}</span>
            <Input
              value={people}
              onChange={(e) => setPeople(e.target.value)}
            />
          </label>
          <p className="label" style={{ margin: 0 }}>
            People only for now: teams arrive with teams themselves. A service account cannot answer for a dataset, and
            Admin › System says whether people, teams or both may. The change is recorded in the audit log.
          </p>
          <div style={{ display: "flex", gap: "var(--sp-8)" }}>
            <Button aria-label={`Save owners of ${dataset.name}`} onClick={save}>
              Save owners
            </Button>
            <Button aria-label={`Cancel changing owner of ${dataset.name}`} onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </fieldset>
      )}
      {problem && <p role="alert">{problem}</p>}
      {said && <p role="status">{said}</p>}
    </div>
  );
}

/** ADR-143 Amendment 2 decisions 1 and 2: every linked case, member or not, with its layer as
 * counts; a removed case's layer offers *Merge into the dataset* and *Delete*, each run dry. */
function LinkedCases({
  api,
  dataset,
  cases,
  onChanged,
}: {
  api: AdminApi;
  dataset: AdminDataset;
  cases: AdminLinkedCase[];
  onChanged: () => void;
}) {
  const [result, setResult] = useState<LayerDryRun | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  // ADR-143 Amendment 5 (L2.5c): what Admin's own Delete said, in the Conduit's words.
  const [deleted, setDeleted] = useState<string | null>(null);
  const dry = (row: AdminLinkedCase, action: LayerDryRun["action"]) => {
    setResult(null);
    setProblem(null);
    setDeleted(null);
    void layerDryRun(api, dataset.id, row.investigation_id, action)
      .then(setResult)
      .catch((e: Error) => setProblem(e.message));
  };
  return (
    <div style={{ display: "grid", gap: "var(--sp-6)" }}>
      <h5 style={{ margin: 0 }}>Linked cases</h5>
      <p className="label" style={{ margin: 0 }}>
        Every case reading this dataset, with its own layer as counts. You see the counts of cases you are not a member
        of, and never what their layers hold.
      </p>
      {cases.length === 0 ? (
        <p style={{ margin: 0 }}>No case reads this dataset.</p>
      ) : (
        <table className="table" aria-label={`Cases linked to ${dataset.name}`}>
          <thead>
            <tr>
              <th>Case</th>
              <th>State</th>
              <th>Items</th>
              <th>Links</th>
              <th>Size</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {cases.map((row) => (
              <tr key={row.investigation_id}>
                <td>
                  {row.name}
                  {row.home_case && <div className="label">Home case</div>}
                  {row.through && <div className="label">{`Through ${row.through}`}</div>}
                </td>
                <td>{row.state === "removed" ? "Removed" : "Open"}</td>
                <td>{row.items}</td>
                <td>{row.links}</td>
                <td>{sizeWords(row.size_bytes)}</td>
                <td>
                  {row.state === "removed" && !row.through && (
                    <div style={{ display: "flex", gap: "var(--sp-6)", flexWrap: "wrap" }}>
                      {dataset.kind !== "composite" && (
                        <Button onClick={() => dry(row, "merge")}>{`Merge ${row.name} into the dataset (dry run)`}</Button>
                      )}
                      <Button onClick={() => dry(row, "delete")}>{`Delete ${row.name}'s layer (dry run)`}</Button>
                    </div>
                  )}
                  {row.state === "removed" && row.through && (
                    <span className="label">{`Read through ${row.through}: deleted there, never merged`}</span>
                  )}
                  {row.state === "removed" && !row.through && dataset.kind === "composite" && (
                    <span className="label">A composite case&apos;s layer cannot be merged: delete it, or leave it</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="label" style={{ margin: 0 }}>
        A dry run writes nothing. Pictures added before this deployment began recording sizes are not counted in a
        layer&apos;s size, and you see the counts only of what you may read yourself.
      </p>
      {problem && <p role="alert">{problem}</p>}
      {result && (
        <p role="status" style={{ margin: 0 }}>
          {`${result.would} ${doneWhere(result.action)}`}
        </p>
      )}
      {result?.action === "delete" && (
        <DeleteLayer
          api={api}
          dataset={dataset}
          row={cases.find((c) => c.investigation_id === result.investigation_id)}
          onDeleted={(words) => {
            setResult(null);
            setDeleted(words);
            onChanged();
          }}
          onProblem={setProblem}
        />
      )}
      {deleted && (
        <p role="status" style={{ margin: 0 }}>
          {deleted}
        </p>
      )}
    </div>
  );
}

/** ADR-143 Amendment 5 decision 7 (L2.5c): Admin's own *Delete*, offered only after its dry run,
 * confirmed by the dry run's words above it; the Conduit refuses another unit's dataset as unknown. */
function DeleteLayer({
  api,
  dataset,
  row,
  onDeleted,
  onProblem,
}: {
  api: AdminApi;
  dataset: AdminDataset;
  row: AdminLinkedCase | undefined;
  onDeleted: (words: string) => void;
  onProblem: (words: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  if (!row) return null;
  return (
    <div style={{ display: "flex", gap: "var(--sp-6)" }}>
      <Button
        disabled={busy}
        onClick={() => {
          setBusy(true);
          void deleteRemovedLayer(api, dataset.id, row.investigation_id)
            .then((done) => onDeleted(done.words))
            .catch((e: Error) => onProblem(e.message))
            .finally(() => setBusy(false));
        }}
      >{`Delete ${row.name}'s layer now`}</Button>
    </div>
  );
}

/** Where the merge or delete itself is done (ADR-143 Amendment 2 decision 1, L3.4): a merge by one
 * of the dataset's Authors, in the Ingest Studio's *4 Runs*, after their own dry run; a delete here
 * too, by Admin's own *Delete* (L2.5c), or there. */
export function doneWhere(action: LayerDryRun["action"]): string {
  return action === "merge"
    ? "One of the dataset's Authors merges it in the Ingest Studio, under 4 Runs, after their own dry run."
    : "Delete it below if these are the right counts; one of the dataset's Authors may also delete it in the Ingest Studio, under 4 Runs.";
}
