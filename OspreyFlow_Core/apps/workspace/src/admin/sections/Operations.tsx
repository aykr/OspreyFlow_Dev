// Admin › Running › Operations (`06_DECISIONS.md` ADR-145 decision 9, O3; Amendment 4 decision 11, R7):
// what ages and when, the promotions waiting for review with their age, *Alert the reviewers and
// administrators after N days*, and then every schedule and its runs (`Schedules.tsx`, which the
// Studio, Monitoring and Reports embed on their own). Behind `operate_schedules`.
import { useEffect, useState } from "react";

import type { OperationsAgeing } from "../../../../../packages/schemas/generated";
import { Button, Input } from "../../design/primitives";
import { operationsAgeing, setPromotionAlertDays, type AdminApi } from "../api";
import { Schedules } from "../Schedules";
import { OperationsFigures } from "../OperationsFigures";

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/London" });

const days = (n: number) => `${n} ${n === 1 ? "day" : "days"}`;

export function Ageing({ api }: { api: AdminApi }) {
  const [ageing, setAgeing] = useState<OperationsAgeing | null>(null);
  const [chosen, setChosen] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(null);

  useEffect(() => {
    operationsAgeing(api)
      .then((a) => {
        setAgeing(a);
        setChosen(String(a.alert_after_days));
      })
      .catch((e: Error) => setProblem(e.message));
  }, [api]);

  const save = () => {
    setProblem(null);
    setSaid(null);
    const n = Number(chosen);
    if (!Number.isInteger(n) || n < 1 || n > 90) {
      setProblem("The number of days must be a whole number from 1 to 90.");
      return;
    }
    setPromotionAlertDays(api, n)
      .then(() => operationsAgeing(api))
      .then((a) => {
        setAgeing(a);
        setSaid(`Reviewers and administrators are now alerted after ${days(a.alert_after_days)}.`);
      })
      .catch((e: Error) => setProblem(e.message));
  };

  return (
    <section aria-label="What ages" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h2 style={{ margin: 0 }}>What ages, and when</h2>
      {ageing && (
        <ul style={{ margin: 0 }}>
          {(ageing.rules ?? []).map((rule) => (
            <li key={rule.what}>
              <strong>{rule.what}.</strong> {rule.then}
            </li>
          ))}
        </ul>
      )}
      {ageing && (
        <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "end", flexWrap: "wrap" }}>
          <label style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span>Alert the reviewers and administrators after N days</span>
            <Input type="number" min={1} max={90} value={chosen} onChange={(e) => setChosen(e.target.value)} />
          </label>
          <Button aria-label="Save when promotions are overdue" onClick={save}>
            Save
          </Button>
        </div>
      )}
      <h2 style={{ margin: 0 }}>Promotions waiting for review</h2>
      {ageing && !ageing.promotions_recorded && (
        <p className="label" style={{ margin: 0 }}>
          Promotions from drawing boards are not recorded yet, so none can wait. They are listed here, with their age,
          once analysts can promote.
        </p>
      )}
      {ageing && ageing.promotions_recorded && (ageing.waiting ?? []).length === 0 && (
        <p className="label" style={{ margin: 0 }}>
          No promotion you may see is waiting for review.
        </p>
      )}
      {ageing && (ageing.waiting ?? []).length > 0 && (
        <table className="table" aria-label="Promotions waiting for review">
          <thead>
            <tr>
              <th scope="col">Load</th>
              <th scope="col">Into</th>
              <th scope="col">Sent by</th>
              <th scope="col">Sent</th>
              <th scope="col">Waiting</th>
            </tr>
          </thead>
          <tbody>
            {(ageing.waiting ?? []).map((p) => (
              <tr key={p.promotion_id}>
                <td>{p.load_id}</td>
                <td>{p.dataset_name}</td>
                <td>{p.proposed_by_name}</td>
                <td>{when(p.proposed_at)}</td>
                <td>{p.overdue ? `${days(p.age_days)}, overdue` : days(p.age_days)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {problem && <p role="alert">{problem}</p>}
      {said && <p role="status">{said}</p>}
    </section>
  );
}

export function Operations({ api }: { api: AdminApi }) {
  return (
    <div style={{ display: "grid", gap: "var(--sp-16)" }}>
      <Ageing api={api} />
      {/* ADR-141 (L1.7, the studio lane by agreement): the runs, the scheduler, external triggers, quotas. */}
      <OperationsFigures api={api} />
      <Schedules api={api} />
    </div>
  );
}
