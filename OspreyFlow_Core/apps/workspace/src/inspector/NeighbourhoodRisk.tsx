// *Neighbourhood risk* for the selected entity (ADR-109 phase E): the case's alerts within two hops,
// each halved per hop and counted for ninety days. Asked on demand and computed by the Conduit as
// this analyst reads the graph — never a stored score, so it says only what their own visible graph
// supports. Each contribution names the entity, how far away it is and what its alerts said.
import { useState } from "react";

import type { NeighbourhoodRisk as Risk, Node } from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives";

export interface NeighbourhoodRiskProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  node: Node;
}

const SCORE = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });

function hopsWords(hops: number): string {
  return hops === 0 ? "this entity" : hops === 1 ? "one hop away" : `${hops} hops away`;
}

export function NeighbourhoodRisk(props: NeighbourhoodRiskProps) {
  const [risk, setRisk] = useState<Risk | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const ask = async () => {
    setBusy(true);
    setProblem(null);
    try {
      const response = await fetch(
        `${props.apiBaseUrl}/v1/investigations/${encodeURIComponent(props.investigationId)}/risk/${encodeURIComponent(props.node.id)}`,
        { headers: { Authorization: `Bearer ${props.bearerToken}` } },
      );
      if (response.ok) {
        setRisk((await response.json()) as Risk);
      } else {
        const body = (await response.json().catch(() => ({}))) as { error?: string; detail?: string };
        setProblem(
          body.error === "neighbourhood_too_large" && body.detail
            ? `Not scored: ${body.detail}.`
            : `The neighbourhood could not be scored (${response.status}).`,
        );
      }
    } catch {
      setProblem("The server could not be reached.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
      <Button onClick={() => void ask()} disabled={busy}>
        {risk ? "Score again" : "Score this neighbourhood"}
      </Button>
      {problem && <p role="alert" style={{ color: "var(--error)", margin: 0 }}>{problem}</p>}
      {risk && (
        <>
          <p style={{ margin: 0 }} role="status">
            Neighbourhood risk {SCORE.format(risk.score)} — alerts within {risk.max_hops} hops, halved per hop, from the last{" "}
            {risk.window_days} days, in what you can see.
          </p>
          {(risk.contributions ?? []).length === 0 ? (
            <p className="label" style={{ margin: 0 }}>No alerts nearby.</p>
          ) : (
            <ul aria-label="What contributes" style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
              {(risk.contributions ?? []).map((c) => (
                <li key={c.node_id} className="label">
                  {c.name}, {hopsWords(c.hops)}: {(c.alert_ids ?? []).length} alert(s), +{SCORE.format(c.contribution)}
                  {(c.summaries ?? []).length > 0 ? ` — ${(c.summaries ?? []).join("; ")}` : ""}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
