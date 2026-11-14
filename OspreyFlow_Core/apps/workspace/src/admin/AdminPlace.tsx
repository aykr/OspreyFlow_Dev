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
import { whyNotByRole } from "../help/roles";
import type { AdminApi } from "./api";
import { onOpening, takeOpening } from "./needsYou/openings";
import SECTIONS from "./sections.json";
import { Audit } from "./sections/Audit";
import { Connections } from "./sections/Connections";
import { Dashboards } from "./sections/Dashboards";
import { Datasets } from "./sections/Datasets";
import { DemoPacks } from "./sections/DemoPacks";
import { GradingScheme } from "./sections/GradingScheme";
import { Maps } from "./sections/Maps";
import { Models } from "./sections/Models";
import { Operations } from "./sections/Operations";
import { People } from "./sections/People";
import { Roles } from "./sections/Roles";
import { System } from "./sections/System";
import "./admin.css";
import { HELP_TITLE } from "../help/roles";
import { RolesHelpPage } from "../help/RolesHelpPage";

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
  "grading-scheme": (api) => <GradingScheme api={api} />,
  dashboards: (api) => <Dashboards api={api} />,
  datasets: (api) => <Datasets api={api} />,
  connections: (api) => <Connections api={api} />,
  // ADR-145 decision 9 (L2.6): what ages and when, then the schedules.
  operations: (api) => <Operations api={api} />,
  system: (api) => <System api={api} />,
  // ADR-135 Amendment 2: engines, each job's default and their keys (platform lane P1).
  models: (api) => <Models api={api} />,
  // ADR-147: the basemap providers, their keys, the local basemap and prefetch (platform lane P3).
  maps: (api) => <Maps api={api} />,
  "demo-packs": (api) => <DemoPacks api={api} />,
  // ADR-145 decision 10 (L2.6).
  audit: (api) => <Audit api={api} />,
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
                  {section.coming ? (
                    // Not built yet: named, never a link (the GOV.UK pass, 14 Nov), with a Coming tag.
                    <span className="admin-nav__coming-item">
                      {section.label}{" "}
                      <strong className={govuk ? "govuk-tag govuk-tag--grey admin-nav__coming" : "label admin-nav__coming"}>Coming</strong>
                      {/* ADR-145 decision 5: it still says what it will hold, here, never behind a link. */}
                      <span className="admin-nav__coming-what">{section.coming}</span>
                    </span>
                  ) : (
                    <button
                      type="button"
                      className={govuk ? "govuk-link admin-nav__link" : "admin-nav__link"}
                      aria-current={section.id === current ? "page" : undefined}
                      onClick={() => onChoose(section.id)}
                    >
                      {section.label}
                    </button>
                  )}
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
  // L2.7: *Needs you* asks for a section (Operations, for an overdue promotion); taken once.
  useEffect(() => {
    const take = () => {
      const opening = takeOpening("admin");
      if (opening) {
        moved.current = true;
        setChosen(opening.section);
      }
    };
    take();
    return onOpening(take);
  }, []);
  useEffect(() => {
    // Choosing a section moves focus to its heading, as a page change would; the first draw does not.
    if (moved.current) heading.current?.focus();
  }, [chosen]);
  const govuk = currentBrand() === "govuk";
  // ADR-145 Amendment 4 decision 12: *Roles, teams and Authors*, the one help page, opened from here.
  const [help, setHelp] = useState(false);
  if (help) {
    return (
      <section aria-label="Admin" className="admin-place">
        <RolesHelpPage backTo="Admin" onBack={() => setHelp(false)} />
      </section>
    );
  }
  return (
    <section aria-label="Admin" className="admin-place">
      {/* "Admin" a caption over the section's own h1, the one heading of the page; the help page a
          link in the same row (the GOV.UK pass, 14 Nov). */}
      <div className="admin-place__title-row">
        <span className={govuk ? "govuk-caption-l admin-place__caption" : "label admin-place__caption"}>Admin</span>
        <button type="button" className={govuk ? "govuk-link admin-place__help" : "admin-row-actions__link admin-place__help"} onClick={() => setHelp(true)}>{HELP_TITLE}</button>
      </div>
      {!section && <p className="label">{`Your account holds no administration right. ${whyNotByRole("administer_system")}`}</p>}
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
            <h1 id="admin-section-title" ref={heading} tabIndex={-1} className={govuk ? "govuk-heading-l admin-place__heading" : "value admin-place__heading"}>
              {section.label}
            </h1>
            {section.coming ? <Coming section={section} /> : SCREENS[section.id]?.(api)}
          </div>
        </div>
      )}
    </section>
  );
}
