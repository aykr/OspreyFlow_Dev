// Home's *What you can do, and what you answer for* (ADR-145 Amendment 4 decision 12; L2.7): the places
// the person can open, what they can do there in plain words, their level in each case, and what they
// answer for with what is waiting, each line opening where to act. *Why can I do this?* names the role
// behind it. What it lists is `answersFor.ts`'s, from the person's own reads alone.
import { useEffect, useState } from "react";

import { readNeedsYou, type NeedsYou } from "../admin/needsYou/needsYouApi";
import { type CaseListing, listCases } from "../investigation/cases";
import { answersFor, type Opens } from "./answersFor";

export interface AnswersForProps {
  apiBaseUrl: string;
  bearerToken: string;
  rights: ReadonlySet<string>;
  roles: readonly string[];
  onOpenCase: (id: string) => void;
  onOpenModel?: (datasetId: string) => void;
  onOpenOperations?: () => void;
  /** For tests: the reads, otherwise the Conduit's. */
  read?: { cases: () => Promise<CaseListing[]>; needs: () => Promise<NeedsYou> };
}

export function AnswersForSection({ apiBaseUrl, bearerToken, rights, roles, onOpenCase, onOpenModel, onOpenOperations, read }: AnswersForProps) {
  const [cases, setCases] = useState<CaseListing[] | null>(null);
  const [needs, setNeeds] = useState<NeedsYou | null>(null);
  const [unread, setUnread] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    const reads = read ?? { cases: () => listCases(apiBaseUrl, bearerToken), needs: () => readNeedsYou(apiBaseUrl, bearerToken) };
    reads
      .cases()
      .then((c) => !cancelled && setCases(c))
      .catch(() => !cancelled && (setCases([]), setUnread((u) => [...u, "your cases"])));
    reads
      .needs()
      .then((n) => !cancelled && setNeeds(n))
      .catch(() => !cancelled && setUnread((u) => [...u, "what waits for you"]));
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, read]);

  const shown = answersFor({ rights, roles, cases: cases ?? [], needs });
  const open = (opens: Opens): (() => void) | null => {
    if (opens.to === "case") return () => onOpenCase(opens.caseId);
    if (opens.to === "model" && onOpenModel) return () => onOpenModel(opens.datasetId);
    if (opens.to === "operations" && onOpenOperations) return onOpenOperations;
    return null;
  };

  return (
    <section aria-labelledby="answers-for" className="home-section">
      <div className="home-section__head">
        <h2 id="answers-for">What you can do, and what you answer for</h2>
      </div>
      {unread.length > 0 && <p role="alert">{`Could not read ${unread.join(" or ")}; what is shown may be short.`}</p>}
      <h3 className="label">Places you can open</h3>
      <ul className="home-facts">
        {shown.places.length === 0 && <li>None yet. Ask an administrator to give you a role.</li>}
        {shown.places.map((p) => (
          <li key={p.key}>
            <strong>{p.name}</strong>: {p.says}
          </li>
        ))}
      </ul>
      <h3 className="label">What you answer for</h3>
      <ul className="home-facts">
        {shown.answers.length === 0 && <li>Nothing waits for you.</li>}
        {shown.answers.map((a, i) => {
          const act = open(a.opens);
          const tip = `answer-why-${i}`;
          return (
            <li key={`${a.text}-${i}`}>
              {act ? (
                <button type="button" className="btn" aria-describedby={tip} onClick={act}>
                  {a.text}
                </button>
              ) : (
                <span aria-describedby={tip} tabIndex={0}>
                  {a.text}
                </span>
              )}
              <span id={tip} className="caption" style={{ display: "block" }}>
                {`Why: ${a.why}`}
              </span>
            </li>
          );
        })}
      </ul>
      {shown.levels.length > 0 && (
        <>
          <h3 className="label">Your level in each case</h3>
          <ul className="home-facts">
            {shown.levels.map((l) => (
              <li key={l.caseId}>{`${l.level} of ${l.name}`}</li>
            ))}
          </ul>
        </>
      )}
      <details>
        <summary className="label">What you can do, by place</summary>
        {shown.can.map((g) => (
          <div key={g.group}>
            <h4 className="label">{g.group}</h4>
            <ul className="home-facts">
              {g.rights.map((r) => (
                <li key={r.right}>
                  <details>
                    <summary>
                      {`${r.name}: ${r.says}`} <span className="caption">Why can I do this?</span>
                    </summary>
                    <span className="caption">{r.why}</span>
                  </details>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </details>
    </section>
  );
}
