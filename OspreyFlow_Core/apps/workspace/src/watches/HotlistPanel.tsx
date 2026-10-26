// A hotlist entry form plus the analyst's own hotlist list — Phase 7 Stage 6c's Glass half,
// `02_GLASS_FRONTEND.md` §3.3: "A list of identifiers with an owner and a review date." Owner-only,
// not investigation-scoped — the same reasoning `QueryBuilderPanel`'s own save/load already gives
// for `/v1/patterns/*`.
//
// **Errors surface as an inline banner, not `ActionErrorOverlay`.** `ActionErrorOverlay`
// (`canvas/ActionErrorOverlay.tsx`) is an x/y-positioned `Popover` built for the canvas, where a
// failure needs to anchor near the cursor/selection that triggered it. This panel is not the
// canvas — it is the same class of surface `QueryBuilderPanel.tsx` already is, and that panel's
// own answer to "no silent drop" is a plain `error` state rendered as a banner, not the canvas's
// overlay. Reused here rather than forcing the overlay onto a surface it was never built for; both
// satisfy the same requirement (a thrown client call is always visible, never swallowed).
import { useEffect, useState } from "react";

import type { Hotlist } from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives/Button";
import { Input } from "../design/primitives/Input";
import { Panel } from "../design/primitives/Panel";
import { createHotlist, listHotlists } from "./api";
import { StatusBadge } from "./StatusBadge";

export interface HotlistPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** ADR-099 Amendment 3: the case whose datasets these are. */
  investigationId: string;
}

export function HotlistPanel({ apiBaseUrl, bearerToken, investigationId }: HotlistPanelProps) {
  const [identifier, setIdentifier] = useState("");
  const [reviewDate, setReviewDate] = useState("");
  const [hotlists, setHotlists] = useState<Hotlist[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Passive list-load — silently leaves the list empty on failure, the same "nothing to surface
    // yet, no error banner before the analyst has done anything" shape `QueryBuilderPanel`'s own
    // mount-time `listPatterns` call already establishes. `handleCreate` surfaces a real `error`
    // for a failure the analyst actually triggered.
    listHotlists(apiBaseUrl, bearerToken, investigationId)
      .then(setHotlists)
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate(): Promise<void> {
    if (!identifier || !reviewDate) return;
    setError(null);
    try {
      await createHotlist(apiBaseUrl, bearerToken, investigationId, { identifier, review_date: reviewDate });
      setIdentifier("");
      setReviewDate("");
      setHotlists(await listHotlists(apiBaseUrl, bearerToken, investigationId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <Panel title="Hotlists" className="hotlist-panel">
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-8)" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
          <Input
            aria-label="Identifier"
            placeholder="Identifier (e.g. MSISDN, email)"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
          />
          <Input
            aria-label="Review date"
            type="date"
            value={reviewDate}
            onChange={(e) => setReviewDate(e.target.value)}
          />
          <Button
            variant="primary"
            onClick={() => void handleCreate()}
            disabled={!identifier || !reviewDate}
          >
            Add to hotlist
          </Button>
        </div>
        {error && (
          <p role="alert" style={{ color: "var(--error)" }}>
            {error}
          </p>
        )}
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {hotlists.map((hotlist) => (
            <li
              key={hotlist.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "var(--sp-4) 0",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              <span className="value">{hotlist.identifier_typed ?? hotlist.identifier}</span>
              {/* ADR-127 decision 7(b): no adapter accepted this text, so it is matched only as
                  written. Said, so a number that will not match its other renderings is no surprise. */}
              {hotlist.identifier_canonical === false ? (
                <span style={{ color: "var(--text-tertiary)" }}>
                  kept as written: matches only this exact text
                </span>
              ) : null}
              <StatusBadge status={hotlist.status ?? "active"} />
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}
