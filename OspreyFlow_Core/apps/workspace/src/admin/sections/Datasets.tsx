// Admin › Data › Datasets (ADR-136 decision 2; ADR-145 decision 5): every dataset and where its
// material may go. Behind `administer_system`.
import { useEffect, useState } from "react";

import type { AdminDataset } from "../../../../../packages/schemas/generated";
import { Button, Select } from "../../design/primitives";
import { listDatasets, setDatasetEgress, type AdminApi } from "../api";

const EGRESS: { value: AdminDataset["egress"]; label: string }[] = [
  { value: "none", label: "none — never sent to a hosted engine" },
  { value: "contracted", label: "contracted — only to a provider under a privacy contract" },
  { value: "any", label: "any — to any enabled provider" },
];

/** ADR-136 decision 2: every dataset and where its material may go when a model is asked. A change
 * is one dataset at a time, saved by its own button, and the Conduit audits it. */
export function Datasets({ api }: { api: AdminApi }) {
  const [datasets, setDatasets] = useState<AdminDataset[] | null>(null);
  const [chosen, setChosen] = useState<Record<string, AdminDataset["egress"]>>({});
  const [said, setSaid] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    listDatasets(api).then(setDatasets).catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);
  const save = (dataset: AdminDataset) => {
    const egress = chosen[dataset.id] ?? dataset.egress;
    setProblem(null);
    setSaid(null);
    void setDatasetEgress(api, dataset.id, egress)
      .then((changed) => {
        setDatasets((current) => (current ?? []).map((d) => (d.id === changed.id ? changed : d)));
        setSaid(`${changed.name}: egress is now ${changed.egress}.`);
      })
      .catch((e: Error) => setProblem(e.message));
  };
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
      {datasets && (
        <table className="table" aria-label="Datasets">
          <thead>
            <tr>
              <th>Dataset</th>
              <th>Unit</th>
              <th>Egress</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {datasets.map((dataset) => (
              <tr key={dataset.id}>
                <td>{dataset.name}</td>
                <td>{dataset.owning_unit}</td>
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
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {datasets?.length === 0 && <p className="label" style={{ margin: 0 }}>There is no dataset yet.</p>}
    </>
  );
}
