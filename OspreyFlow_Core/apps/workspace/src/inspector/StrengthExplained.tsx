// A selected link's connection strength, explained (ADR-139 decision 9): its count against what is
// heavy for its type, its recency, the rule and version applied, each influencer that changed it
// (naming the kind of record that evidenced it), and what its two ends share, ranked by rarity.
// ADR-139 Amendment 2: the composition and the rarity measure are named, and under client parity the
// raw sum on the client's scale is shown beside the drawn strength, so their thresholds compare.
// Read from the store as the reader, so it never says a count from beyond what they may see.
import { useEffect, useState } from "react";

import type { Edge, LinkStrength, PairRarity } from "../../../../packages/schemas/generated";
import { nodeLabel } from "../canvas/nodeAttributes";
import { fetchConnectionStrengths, fetchRarity } from "../strength/api";
import {
  COMPOSITION_LABEL,
  MEASURE_LABEL,
  strengthExplanation,
  type Composition,
  type LinkName,
  type RarityMeasure,
} from "../strength/words";

const SCORE = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const EXACT = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 4, maximumFractionDigits: 4 });

export interface StrengthExplainedProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  edge: Edge;
  linkName?: LinkName;
}

export interface PairSharedProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  a: string;
  b: string;
}

/** Two entities' shared attributes, rarest first, and their rarity (ADR-139 decision 9): for a
 * link's two ends, or for two nodes selected together. */
export function PairShared({ apiBaseUrl, bearerToken, investigationId, a, b }: PairSharedProps) {
  const [pair, setPair] = useState<PairRarity | null>(null);
  const [measure, setMeasure] = useState<RarityMeasure>("share");
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setPair(null);
    setProblem(null);
    void fetchRarity(apiBaseUrl, bearerToken, investigationId, "dataset", [[a, b]])
      .then((rarity) => {
        if (cancelled) return;
        setPair(rarity.pairs[0] ?? null);
        setMeasure((rarity.measure ?? "share") as RarityMeasure);
      })
      .catch((err: unknown) => {
        if (!cancelled) setProblem(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, a, b]);

  if (problem) return <p className="strength-explained__problem">{problem}</p>;
  if (!pair) return <p className="strength-explained__muted">Working out what they share…</p>;
  const shared = pair.shared ?? [];
  return (
    <>
      <p className="strength-explained__heading">What they share, rarest first</p>
      {pair.score === null || pair.score === undefined ? (
        <p className="strength-explained__muted">
          No rarity to give: they are of different kinds, or share no dataset.
        </p>
      ) : shared.length === 0 ? (
        <p className="strength-explained__muted">They share nothing you can see.</p>
      ) : (
        <>
          <ol aria-label="Shared attributes, rarest first" className="strength-explained__shared">
            {shared.map((s) => (
              <li key={s.node.id}>
                <span>
                  {s.node.type} · {nodeLabel(s.node)}
                </span>
                <span className="value">{SCORE.format(s.score)}</span>
              </li>
            ))}
          </ol>
          <p className="strength-explained__muted">
            Shared-attribute rarity {SCORE.format(pair.score)}
            {pair.dataset ? `, worked out in ${pair.dataset}` : ""}, over what you may see; measured by{" "}
            {MEASURE_LABEL[measure]}.
          </p>
          {pair.parity_raw !== null && pair.parity_raw !== undefined && (
            <p className="strength-explained__muted" aria-label="Client parity through what they share">
              Client parity through what they share: raw sum {EXACT.format(pair.parity_raw)} on the client's scale
              {(pair.parity_applied ?? []).length > 0
                ? ` (rarity and ${(pair.parity_applied ?? []).map((x) => x.label).join(", ")})`
                : " (rarity alone)"}
              ; drawn at {SCORE.format(pair.parity_strength ?? 0)}.
            </p>
          )}
        </>
      )}
    </>
  );
}

export function StrengthExplained({ apiBaseUrl, bearerToken, investigationId, edge, linkName }: StrengthExplainedProps) {
  const [link, setLink] = useState<LinkStrength | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLink(null);
    setProblem(null);
    void fetchConnectionStrengths(apiBaseUrl, bearerToken, investigationId, [edge.id])
      .then((strengths) => {
        if (!cancelled) setLink(strengths.links.find((l) => l.edge_id === edge.id) ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setProblem(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, edge.id]);

  if (problem) return <p className="strength-explained__problem">{problem}</p>;
  if (!link) return <p className="strength-explained__muted">Working out this link's strength…</p>;
  const composition = (link.composition ?? "standard") as Composition;
  return (
    <div className="strength-explained">
      <p className="strength-explained__heading" aria-label="Composition">
        Composition: {COMPOSITION_LABEL[composition]}
      </p>
      {composition === "client_parity" && link.raw_sum !== null && link.raw_sum !== undefined && (
        <p className="strength-explained__raw" aria-label="Raw sum on the client's scale">
          <span>Raw sum, the client's scale</span>
          <span className="value">{EXACT.format(link.raw_sum)}</span>
        </p>
      )}
      <ul aria-label="What this link's strength rests on" className="strength-explained__lines">
        {strengthExplanation(link, linkName).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <PairShared
        apiBaseUrl={apiBaseUrl}
        bearerToken={bearerToken}
        investigationId={investigationId}
        a={edge.source}
        b={edge.target}
      />
    </div>
  );
}
