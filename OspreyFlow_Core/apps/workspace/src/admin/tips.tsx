// Admin's tips (ADR-145 Amendment 4 decision 12; L2.7): every role, level, team, lead and a dataset's
// Authors has a short tip where it appears, read with the control it explains (`aria-describedby`),
// in the words of `help/roles.ts`, the one source the help page and the guides take too. A tip names
// roles by their names and never a person or an id (`adminWords.test.tsx`).
import type { ReactNode } from "react";

import { LEVEL_WORDS, PLACE_WORDS, ROLE_WORDS, TEAM_WORDS, rightName } from "../help/roles";

/** The id a role's tip is drawn under, for `aria-describedby`. */
export const roleTipId = (role: string) => `role-tip-${role.replace(/[^A-Za-z0-9-]/g, "-")}`;
export const LEVELS_TIP_ID = "levels-tip";
export const TEAM_TIP_ID = "team-tip";
export const LEAD_TIP_ID = "lead-tip";
export const AUTHORS_TIP_ID = "authors-tip";

/** A role's tip: what it lets a person do and the places it opens. */
export function roleTip(role: string): string | null {
  const said = ROLE_WORDS[role];
  if (!said) return null;
  const places = said.places.map((p) => PLACE_WORDS[p].name);
  return places.length ? `${said.says} Opens ${places.join(", ")}.` : said.says;
}

/** A role by its name, never its id (a preset's roles, a grant). */
export function roleName(role: string): string {
  return ROLE_WORDS[role]?.name ?? role;
}

/** A grant as People shows it: a single right by its name, a built-in role by its name; never the
 * grant's own id (`right:read_export_ledger`). */
export function grantWords(grant: string): string {
  if (grant.startsWith("right:")) return `${rightName(grant.slice("right:".length))} (a single right)`;
  return roleName(grant);
}

export function Tip({ id, children }: { id: string; children: ReactNode }) {
  return (
    <span id={id} className="caption admin-tip" style={{ display: "block" }}>
      {children}
    </span>
  );
}

/** What each built-in role lets a person do, and what each case level means, above People's table:
 * each role's box and each person's levels are read with these. */
export function RoleAndLevelTips({ roles }: { roles: readonly { id: string; label: string }[] }) {
  return (
    <details className="admin-tips">
      <summary className="label">What each role and level lets a person do</summary>
      <dl style={{ margin: 0, display: "grid", gap: "var(--sp-4)" }}>
        {roles.map((r) => (
          <div key={r.id}>
            <dt className="value">{r.label}</dt>
            <dd id={roleTipId(r.id)} className="caption" style={{ margin: 0 }}>
              {roleTip(r.id) ?? ""}
            </dd>
          </div>
        ))}
        <div>
          <dt className="value">Levels in a case</dt>
          <dd id={LEVELS_TIP_ID} className="caption" style={{ margin: 0 }}>
            {Object.values(LEVEL_WORDS)
              .map((l) => `${l.name}: ${l.says}`)
              .join(" ")}
          </dd>
        </div>
      </dl>
    </details>
  );
}

export const TIPS = { team: TEAM_WORDS.team, lead: TEAM_WORDS.lead, authors: TEAM_WORDS.authors };
