// The Admin place (`06_DECISIONS.md` ADR-110 Amendments 1 and 14, ADR-112, ADR-145 decisions 5 and
// 13): the deployment's administration inside the running system, behind the same sign-in. A side
// list of sections in their groups (`sections.json`), each shown only to an account holding its
// right, the Conduit refusing anything a stale view still offers (rule 3,
// `test_admin_sections.py`). A section not built yet is a "coming" placeholder, shown only to holders
// of its right; nothing behind it calls the Conduit. Each built section's screen is its own file under
// `sections/`, which is how the section test finds the routes it calls. Under the GOV.UK brand the
// list is a GOV.UK side navigation (decision 13).
import { useEffect, useRef, useState, type ReactNode } from "react";

import { currentBrand } from "../brand/brand";
import type { AdminApi } from "./api";
import SECTIONS from "./sections.json";
import { Connections } from "./sections/Connections";
import { Dashboards } from "./sections/Dashboards";
import { Datasets } from "./sections/Datasets";
import { DemoPacks } from "./sections/DemoPacks";
import { Models } from "./sections/Models";
import { People } from "./sections/People";
import { ProposedTypesSection } from "./sections/ProposedTypes";
import { Roles } from "./sections/Roles";
import { Schedules } from "./Schedules";
import { System } from "./sections/System";
import "./admin.css";

export { feedFreshness } from "./sections/Dashboards";
export { joinWords, removalWords, ROLES } from "./sections/People";

export interface AdminPlaceProps extends AdminApi {
  rights: ReadonlySet<string>;
}

export interface AdminSection {
  id: string;
  label: string;
  right: string;
  /** The file drawing it, from `src/`, for a built section. */
  screen?: string;
  /** What it will hold, for a section not built yet. */
  coming?: string;
}
export interface AdminGroup {
  label: string;
  sections: AdminSection[];
}

export const ADMIN_GROUPS: AdminGroup[] = SECTIONS.groups;

/** Each built section's screen, by its id in `sections.json` (`AdminSections.test.tsx` holds their
 * ids together; `test_admin_sections.py` holds each to the file `sections.json` names). */
export const SCREENS: Record<string, (api: AdminApi) => ReactNode> = {
  people: (api) => <People api={api} />,
  roles: (api) => <Roles api={api} />,
  dashboards: (api) => <Dashboards api={api} />,
  datasets: (api) => <Datasets api={api} />,
  connections: (api) => <Connections api={api} />,
  "proposed-types": (api) => <ProposedTypesSection api={api} />,
  operations: (api) => <Schedules api={api} />,
  system: (api) => <System api={api} />,
  // ADR-135 Amendment 2: engines, each job's default and their keys (platform lane P1).
  models: (api) => <Models api={api} />,
  "demo-packs": (api) => <DemoPacks api={api} />,
};

/** The groups and sections this person's rights show, in their order; a group with none is left out. */
export function sectionsFor(rights: ReadonlySet<string>): AdminGroup[] {
  return ADMIN_GROUPS.map((g) => ({ ...g, sections: g.sections.filter((s) => rights.has(s.right)) })).filter(
    (g) => g.sections.length > 0,
  );
}

function Coming({ section }: { section: AdminSection }) {
  return (
    <p className="label" style={{ margin: 0 }}>
      {`Coming: ${section.coming}`}
    </p>
  );
}

function SideNavigation({
  groups,
  current,
  onChoose,
  govuk,
}: {
  groups: AdminGroup[];
  current: string;
  onChoose: (id: string) => void;
  govuk: boolean;
}) {
  return (
    <nav aria-label="Admin sections" className={govuk ? "admin-nav admin-nav--govuk" : "admin-nav"}>
      {groups.map((group) => {
        // A group of one section of its own name (Audit, Demo packs) is that section alone, unheaded.
        const alone = group.sections.length === 1 && group.sections[0]!.label === group.label;
        return (
          <div key={group.label} className="admin-nav__group">
            {!alone && <h3 className={govuk ? "govuk-heading-s admin-nav__heading" : "label admin-nav__heading"}>{group.label}</h3>}
            <ul className="admin-nav__list">
              {group.sections.map((section) => (
                <li key={section.id} className={section.id === current ? "admin-nav__item admin-nav__item--current" : "admin-nav__item"}>
                  <button
                    type="button"
                    className={govuk ? "govuk-link admin-nav__link" : "admin-nav__link"}
                    aria-current={section.id === current ? "page" : undefined}
                    onClick={() => onChoose(section.id)}
                  >
                    {/* One text, as the banner's coming Boards is: its name is what it reads. */}
                    {section.coming ? `${section.label} (coming)` : section.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

export function AdminPlace({ rights, ...api }: AdminPlaceProps) {
  const groups = sectionsFor(rights);
  const shown = groups.flatMap((g) => g.sections);
  const [chosen, setChosen] = useState<string | null>(null);
  // The first built section the person holds opens first; a placeholder only when nothing else shows.
  const section = shown.find((s) => s.id === chosen) ?? shown.find((s) => s.screen) ?? shown[0];
  const heading = useRef<HTMLHeadingElement>(null);
  const moved = useRef(false);
  useEffect(() => {
    // Choosing a section moves focus to its heading, as a page change would; the first draw does not.
    if (moved.current) heading.current?.focus();
  }, [chosen]);
  const govuk = currentBrand() === "govuk";
  return (
    <section aria-label="Admin" className="admin-place">
      <h2 className={govuk ? "govuk-heading-l admin-place__title" : "value admin-place__title"}>Admin</h2>
      {!section && <p className="label">Your account holds no administration right.</p>}
      {section && (
        <div className="admin-place__body">
          <SideNavigation
            groups={groups}
            current={section.id}
            govuk={govuk}
            onChoose={(id) => {
              moved.current = true;
              setChosen(id);
            }}
          />
          <div className="admin-place__section" role="region" aria-labelledby="admin-section-title">
            <h3 id="admin-section-title" ref={heading} tabIndex={-1} className={govuk ? "govuk-heading-m" : "value"} style={{ margin: 0 }}>
              {section.label}
            </h3>
            {section.coming ? <Coming section={section} /> : SCREENS[section.id]?.(api)}
          </div>
        </div>
      )}
    </section>
  );
}
