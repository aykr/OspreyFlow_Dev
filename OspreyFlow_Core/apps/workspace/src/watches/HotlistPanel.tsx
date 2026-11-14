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
//
// **Who its alerts reach (ADR-133 ruling 3).** A hotlist's alerts reach its owner alone, or also the
// owner's team, in the Monitoring place's one queue. A new hotlist starts from the deployment's
// default; the owner chooses, or changes it later, only where the deployment lets them — otherwise
// the panel says what the deployment has set, and offers no choice.
import { useEffect, useState } from "react";

import type { Hotlist } from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives/Button";
import { Input } from "../design/primitives/Input";
import { Panel } from "../design/primitives/Panel";
import { Select } from "../design/primitives/Select";
import { createHotlist, readHotlists, setHotlistAudience, type HotlistAudience } from "./api";
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
  const [said, setSaid] = useState<string | null>(null);
  const [editable, setEditable] = useState(true);
  const [fixedAudience, setFixedAudience] = useState<HotlistAudience>("only_me");
  const [audience, setAudience] = useState<HotlistAudience>("only_me");

  function take(read: Awaited<ReturnType<typeof readHotlists>>): void {
    setHotlists(read.hotlists);
    setEditable(read.audienceEditable);
    setFixedAudience(read.audienceDefault);
  }

  useEffect(() => {
    // Passive list-load — silently leaves the list empty on failure, the same "nothing to surface
    // yet, no error banner before the analyst has done anything" shape `QueryBuilderPanel`'s own
    // mount-time `listPatterns` call already establishes. `handleCreate` surfaces a real `error`
    // for a failure the analyst actually triggered.
    readHotlists(apiBaseUrl, bearerToken, investigationId)
      .then((read) => {
        take(read);
        setAudience(read.audienceDefault);
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate(): Promise<void> {
    if (!identifier || !reviewDate) return;
    setError(null);
    try {
      await createHotlist(apiBaseUrl, bearerToken, investigationId, {
        identifier,
        review_date: reviewDate,
        ...(editable ? { audience } : {}),
      });
      setIdentifier("");
      setReviewDate("");
      take(await readHotlists(apiBaseUrl, bearerToken, investigationId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function changeAudience(hotlist: Hotlist, next: HotlistAudience): Promise<void> {
    setError(null);
    setSaid(null);
    const shown = hotlist.identifier_typed ?? hotlist.identifier;
    try {
      const changed = await setHotlistAudience(apiBaseUrl, bearerToken, investigationId, hotlist.id, next);
      setHotlists((all) => all.map((h) => (h.id === changed.id ? changed : h)));
      setSaid(next === "team" ? `Alerts from ${shown} now reach your team too.` : `Alerts from ${shown} now reach only you.`);
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
            placeholder="Identifier (e.g. MSISDN, email, account number)"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
          />
          <Input
            aria-label="Review date"
            type="date"
            value={reviewDate}
            onChange={(e) => setReviewDate(e.target.value)}
          />
          {editable ? (
            <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
              Who its alerts reach
              <Select
                aria-label="Who its alerts reach"
                value={audience}
                onChange={(e) => setAudience(e.target.value as HotlistAudience)}
              >
                <option value="only_me">Only me</option>
                <option value="team">Me and my team</option>
              </Select>
            </label>
          ) : (
            <p className="label" style={{ margin: 0 }}>
              {`${AUDIENCE_FIXED[fixedAudience]} The deployment sets this.`}
            </p>
          )}
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
        {said && (
          <p role="status" className="label">
            {said}
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
              {editable ? (
                <Select
                  aria-label={`Who alerts from ${hotlist.identifier_typed ?? hotlist.identifier} reach`}
                  value={hotlist.audience ?? "only_me"}
                  onChange={(e) => void changeAudience(hotlist, e.target.value as HotlistAudience)}
                >
                  <option value="only_me">Only me</option>
                  <option value="team">Me and my team</option>
                </Select>
              ) : (
                <span className="label">{AUDIENCE_FIXED[hotlist.audience ?? "only_me"]}</span>
              )}
              <StatusBadge status={hotlist.status ?? "active"} why={hotlist.stopped_why} />
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}

const AUDIENCE_FIXED: Record<HotlistAudience, string> = {
  only_me: "Alerts reach only you.",
  team: "Alerts reach you and your team.",
};
