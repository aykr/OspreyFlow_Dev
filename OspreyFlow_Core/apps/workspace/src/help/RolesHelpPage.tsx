// The *Roles, teams and Authors* help page (ADR-145 Amendment 4 decision 12): one page, opened from
// Admin and from the Ingest Studio, its words all from `roles.ts`. A page of words: headings for each
// part, lists beneath, and a way back that has focus when it opens (rule 13).
import { useEffect, useRef } from "react";

import { HELP_TITLE, LEVEL_WORDS, PLACE_WORDS, RIGHT_WORDS, ROLE_WORDS, TEAM_WORDS, rightName, rightSays, type Right } from "./roles";

export interface RolesHelpPageProps {
  /** Where the page goes back to: "Admin" or "the Ingest Studio". */
  backTo: string;
  onBack: () => void;
}

const list = { margin: 0, paddingLeft: "var(--sp-16)", display: "grid", gap: "var(--sp-4)" } as const;

export function RolesHelpPage({ backTo, onBack }: RolesHelpPageProps) {
  const back = useRef<HTMLButtonElement>(null);
  useEffect(() => back.current?.focus(), []);
  return (
    <article aria-labelledby="roles-help-title" style={{ flex: 1, overflowY: "auto", padding: "var(--sp-16)", display: "grid", gap: "var(--sp-16)", alignContent: "start", maxWidth: "60rem" }}>
      <div>
        <button ref={back} type="button" className="btn" onClick={onBack}>{`← Back to ${backTo}`}</button>
      </div>
      <h2 id="roles-help-title" style={{ margin: 0 }}>{HELP_TITLE}</h2>
      <section aria-labelledby="help-places">
        <h3 id="help-places">The places</h3>
        <dl style={{ margin: 0 }}>
          {Object.values(PLACE_WORDS).map((p) => (
            <div key={p.name}><dt className="value">{p.name}</dt><dd style={{ margin: "0 0 var(--sp-8)" }}>{p.says}</dd></div>
          ))}
        </dl>
      </section>
      <section aria-labelledby="help-roles">
        <h3 id="help-roles">Roles</h3>
        <dl style={{ margin: 0 }}>
          {Object.values(ROLE_WORDS).map((r) => (
            <div key={r.name}>
              <dt className="value">{r.name}</dt>
              <dd style={{ margin: "0 0 var(--sp-8)" }}>{`${r.says} Opens ${r.places.map((p) => PLACE_WORDS[p].name).join(", ")}.`}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section aria-labelledby="help-levels">
        <h3 id="help-levels">Your level in a case</h3>
        <dl style={{ margin: 0 }}>
          {Object.values(LEVEL_WORDS).map((l) => (
            <div key={l.name}><dt className="value">{l.name}</dt><dd style={{ margin: "0 0 var(--sp-8)" }}>{l.says}</dd></div>
          ))}
        </dl>
      </section>
      <section aria-labelledby="help-teams">
        <h3 id="help-teams">Teams, leads and Authors</h3>
        <ul style={list}>
          <li>{TEAM_WORDS.team}</li>
          <li>{TEAM_WORDS.lead}</li>
          <li>{TEAM_WORDS.authors}</li>
        </ul>
      </section>
      <section aria-labelledby="help-rights">
        <h3 id="help-rights">What each right lets you do</h3>
        <dl style={{ margin: 0 }}>
          {(Object.keys(RIGHT_WORDS) as Right[]).map((right) => [right, rightSays(right)] as const).map(([right, says]) => (
            <div key={right}><dt className="value">{rightName(right)}</dt><dd style={{ margin: "0 0 var(--sp-8)" }}>{says}</dd></div>
          ))}
        </dl>
      </section>
    </article>
  );
}
