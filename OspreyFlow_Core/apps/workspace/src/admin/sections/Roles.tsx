// Admin › People › Roles (ADR-145 decision 7 and Amendment 5; ADR-112 Amendments 4 and 5): the
// built-in roles and the Super user preset, each copied into a new role and never edited; custom
// roles, a name and a set of rights grouped by place, versioned; and teams, each a custom role
// with a mailbox, a lead and a cover. Every refusal is the Conduit's own, in its words: the form
// never refuses in its stead. Behind `manage_people` (`admin/sections.json`).
import { useEffect, useState } from "react";

import type { BuiltInRole, CustomRole, CustomRoleVersion, RolesCatalogue, Team } from "../../../../../packages/schemas/generated";
import { Button, Input, Select } from "../../design/primitives";
import { changeRole, createRole, listRoles, makeTeam, roleVersions, setTeamCover, setTeamLead, type AdminApi } from "../api";

/** The rights grouped as the places they work in (decision 7); a right named in no group is still
 * offered, under *Other*, so no right is ever left out of the form. */
export const RIGHT_GROUPS: { label: string; rights: string[] }[] = [
  { label: "Cases", rights: ["create_case", "share_case", "remove_case", "export", "export_override"] },
  {
    label: "Investigation (the Glass)",
    rights: ["investigate", "edit_graph", "confirm_inferred", "extract_files", "resolve_entities", "record_assessment",
             "ask_model", "run_analysis", "propose_link_type", "manage_strength_influencers", "draw_on_boards",
             "promote_to_dataset", "propose_types"],  // prettier-ignore
  },
  {
    label: "Alerts and rules",
    rights: ["read_alert_queue", "triage_alerts", "author_rules", "deploy_rules", "read_rule_audit", "read_held_rows",
             "decide_held_rows", "trace_ownership", "keep_watches", "load_screening_lists"],  // prettier-ignore
  },
  {
    label: "Ingest Studio",
    rights: ["edit_pipelines", "verify_pipelines", "publish_pipelines", "run_pipelines", "schedule_pipelines",
             "add_ingest_files", "revert_loads", "edit_target_model", "review_promotions", "accept_types", "merge_datasets"],  // prettier-ignore
  },
  { label: "Reporting", rights: ["read_reports", "read_report_feed", "read_data_feeds"] },
  {
    label: "Administration",
    rights: ["administer_system", "manage_people", "manage_dashboards", "operate_schedules", "manage_ontology",
             "manage_geospatial", "read_audit", "read_export_ledger", "manage_models"],  // prettier-ignore
  },
];

/** A right's name in words: `review_promotions` reads "Review promotions". */
export const rightWords = (right: string) => {
  const words = right.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
};

/** Every right offered, by group, with any the groups do not name under *Other*. */
export function groupsFor(all: string[]): { label: string; rights: string[] }[] {
  const named = new Set(RIGHT_GROUPS.flatMap((g) => g.rights));
  const groups = RIGHT_GROUPS.map((g) => ({ label: g.label, rights: g.rights.filter((r) => all.includes(r)) }));
  const other = all.filter((r) => !named.has(r));
  return [...groups, ...(other.length ? [{ label: "Other", rights: other }] : [])].filter((g) => g.rights.length);
}

function RoleForm({
  title,
  start,
  all,
  onSave,
  onCancel,
}: {
  title: string;
  start: { id: string | null; name: string; rights: string[] };
  all: string[];
  onSave: (name: string, rights: string[]) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(start.name);
  const [chosen, setChosen] = useState(new Set(start.rights));
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <form
      aria-label={title}
      className="admin-role-form"
      style={{ display: "grid", gap: "var(--sp-8)", border: "1px solid var(--line)", padding: "var(--sp-8)" }}
      onSubmit={(e) => {
        e.preventDefault();
        setProblem(null);
        void onSave(name, [...chosen].sort()).catch((err: Error) => setProblem(err.message));
      }}
    >
      <h3 style={{ margin: 0 }}>{title}</h3>
      {problem && (
        <div role="alert" className="govuk-error-summary-like" style={{ border: "2px solid var(--danger)", padding: "var(--sp-8)" }}>
          <p style={{ margin: 0 }}>{`There is a problem: ${problem}`}</p>
        </div>
      )}
      <label className="label">
        Role name
        <Input aria-label="Role name" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      {groupsFor(all).map((group) => (
        <fieldset key={group.label} style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="label">{group.label}</legend>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)" }}>
            {group.rights.map((right) => (
              <label key={right} className="label">
                <input
                  type="checkbox"
                  aria-label={rightWords(right)}
                  checked={chosen.has(right)}
                  onChange={(e) => {
                    const next = new Set(chosen);
                    if (e.target.checked) next.add(right);
                    else next.delete(right);
                    setChosen(next);
                  }}
                />{" "}
                {rightWords(right)}
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
        <Button type="submit" aria-label={start.id ? `Save ${start.name}` : "Save new role"}>
          Save
        </Button>
        <Button type="button" aria-label={start.id ? `Cancel editing ${start.name}` : "Cancel the new role"} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function TeamEditor({ api, role, onSaved }: { api: AdminApi; role: CustomRole; onSaved: (team: Team) => void }) {
  const team = role.team;
  const [displayName, setDisplayName] = useState(team?.display_name ?? role.name);
  const [mailbox, setMailbox] = useState(team?.mailbox ?? "");
  const [lead, setLead] = useState(team?.lead ?? "");
  const [cover, setCover] = useState(team?.cover ?? "");
  const [until, setUntil] = useState(team?.cover_until ?? "");
  const [said, setSaid] = useState<string | null>(null);
  const members = team?.members ?? [];
  const done = (p: Promise<Team>, words: string) =>
    void p
      .then((saved) => {
        setSaid(words);
        onSaved({ ...saved, members: saved.members?.length ? saved.members : members });
      })
      .catch((e: Error) => setSaid(e.message));
  const who = (id: string | null | undefined) => members.find((m) => m.id === id)?.name ?? id ?? "nobody";
  return (
    <div style={{ display: "grid", gap: "var(--sp-8)", border: "1px solid var(--line)", padding: "var(--sp-8)" }}>
      <p className="label" style={{ margin: 0 }}>
        A team is this role's holders. It can hold a level in a case and own a dataset; its mailbox is a contact, never a
        sign-in.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)", alignItems: "end" }}>
        <label className="label">
          Team name
          <Input aria-label={`Team name for ${role.name}`} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </label>
        <label className="label">
          Team mailbox
          <Input aria-label={`Team mailbox for ${role.name}`} type="email" value={mailbox} onChange={(e) => setMailbox(e.target.value)} />
        </label>
        <Button
          aria-label={team ? `Save team ${role.name}` : `Make a team of ${role.name}`}
          onClick={() => done(makeTeam(api, role.id, displayName, mailbox), team ? "Team saved." : "Made a team.")}
        >
          {team ? "Save team" : "Make a team"}
        </Button>
      </div>
      {team && (
        <>
          <p style={{ margin: 0 }}>
            {`Lead: ${who(team.lead)}${team.cover ? `; covering until ${team.cover_until}: ${who(team.cover)}` : ""}. Acting today: ${who(team.acting_lead)}.`}
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)", alignItems: "end" }}>
            <label className="label">
              Lead
              <Select aria-label={`Lead of ${team.display_name}`} value={lead} onChange={(e) => setLead(e.target.value)}>
                <option value="">Choose a member</option>
                {members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name ?? m.id}
                  </option>
                ))}
              </Select>
            </label>
            <Button
              aria-label={`${team.lead ? "Hand over" : "Name"} the lead of ${team.display_name}`}
              disabled={!lead}
              onClick={() => done(setTeamLead(api, role.id, lead), "Lead saved.")}
            >
              {team.lead ? "Hand over" : "Name"}
            </Button>
            <label className="label">
              Cover
              <Select aria-label={`Cover for ${team.display_name}`} value={cover} onChange={(e) => setCover(e.target.value)}>
                <option value="">No cover</option>
                {members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name ?? m.id}
                  </option>
                ))}
              </Select>
            </label>
            <label className="label">
              Last day
              <Input aria-label={`Cover's last day for ${team.display_name}`} type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
            </label>
            <Button
              aria-label={`${cover ? "Save cover" : "End cover"} for ${team.display_name}`}
              onClick={() => done(setTeamCover(api, role.id, cover || null, cover ? until : null), cover ? "Cover saved." : "Cover ended.")}
            >
              {cover ? "Save cover" : "End cover"}
            </Button>
          </div>
        </>
      )}
      {said && (
        <p role="status" className="label" style={{ margin: 0 }}>
          {said}
        </p>
      )}
    </div>
  );
}

export function Roles({ api }: { api: AdminApi }) {
  const [catalogue, setCatalogue] = useState<RolesCatalogue | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [form, setForm] = useState<{ title: string; id: string | null; name: string; rights: string[] } | null>(null);
  const [teamOf, setTeamOf] = useState<string | null>(null);
  const [versions, setVersions] = useState<{ id: string; list: CustomRoleVersion[] } | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const read = () => listRoles(api).then(setCatalogue).catch((e: Error) => setProblem(e.message));
  useEffect(() => {
    void read();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);
  if (problem) return <p role="alert">{problem}</p>;
  if (!catalogue) return <p className="label">Reading the roles…</p>;
  const builtIn = catalogue.built_in ?? [];
  const custom = catalogue.custom ?? [];
  const all = [...new Set(builtIn.flatMap((r) => r.rights))].sort();
  const copy = (role: BuiltInRole | CustomRole, label: string) =>
    setForm({ title: "New role", id: null, name: `${label} (copy)`, rights: [...role.rights] });
  return (
    <>
      <p className="label" style={{ margin: 0 }}>
        A role is a set of rights: what a person may do, never what they may see. Built-in roles are copied, never edited. No role both proposes
        and approves the same kind of decision, and you cannot give an administration right you do not hold.
      </p>
      {said && (
        <p role="status" style={{ margin: 0 }}>
          {said}
        </p>
      )}
      <table className="table" aria-label="Built-in roles">
        <thead>
          <tr>
            <th>Role</th>
            <th>Rights</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {builtIn.map((role) => (
            <tr key={role.id}>
              <td>
                <span className="value">{role.label}</span>
                {role.gives?.length ? (
                  <>
                    <br />
                    <span className="label">{`A preset: gives ${role.gives.join(", ")} together`}</span>
                  </>
                ) : null}
              </td>
              <td className="label">{role.rights.map(rightWords).join(", ")}</td>
              <td>
                <Button aria-label={`Copy ${role.label} into a new role`} onClick={() => copy(role, role.label)}>
                  Copy
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="table" aria-label="Custom roles">
        <thead>
          <tr>
            <th>Role</th>
            <th>Rights</th>
            <th>Held by</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {custom.length === 0 && (
            <tr>
              <td colSpan={4} className="label">
                No custom roles yet.
              </td>
            </tr>
          )}
          {custom.map((role) => (
            <tr key={role.id}>
              <td>
                <span className="value">{role.name}</span>
                <br />
                <span className="label">{`v${role.version}${role.team ? ` · team ${role.team.display_name}, ${role.team.mailbox}` : ""}`}</span>
              </td>
              <td className="label">{role.rights.map(rightWords).join(", ")}</td>
              <td className="label">{`${role.holders} ${role.holders === 1 ? "person" : "people"}`}</td>
              <td>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-4)" }}>
                  <Button
                    aria-label={`Edit ${role.name}`}
                    onClick={() => setForm({ title: `Edit ${role.name}`, id: role.id, name: role.name, rights: [...role.rights] })}
                  >
                    Edit
                  </Button>
                  <Button aria-label={`Copy ${role.name} into a new role`} onClick={() => copy(role, role.name)}>
                    Copy
                  </Button>
                  <Button
                    aria-label={`Versions of ${role.name}`}
                    aria-expanded={versions?.id === role.id}
                    onClick={() =>
                      versions?.id === role.id
                        ? setVersions(null)
                        : void roleVersions(api, role.id)
                            .then((list) => setVersions({ id: role.id, list }))
                            .catch((e: Error) => setSaid(e.message))
                    }
                  >
                    Versions
                  </Button>
                  <Button aria-label={`Team for ${role.name}`} aria-expanded={teamOf === role.id} onClick={() => setTeamOf(teamOf === role.id ? null : role.id)}>
                    Team
                  </Button>
                </div>
                {versions?.id === role.id && (
                  <ol aria-label={`Versions of ${role.name}`} className="label" style={{ margin: 0 }}>
                    {versions.list.map((v) => (
                      <li key={v.version}>{`v${v.version}, ${v.changed_at.slice(0, 10)} by ${v.changed_by}: ${v.rights.map(rightWords).join(", ")}`}</li>
                    ))}
                  </ol>
                )}
                {teamOf === role.id && (
                  <TeamEditor
                    api={api}
                    role={role}
                    onSaved={(team) =>
                      setCatalogue((c) => c && { ...c, custom: c.custom.map((r) => (r.id === role.id ? { ...r, team } : r)) })
                    }
                  />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {form ? (
        <RoleForm
          key={`${form.id ?? "new"}-${form.name}`}
          title={form.title}
          start={form}
          all={all}
          onCancel={() => setForm(null)}
          onSave={async (name, rights) => {
            const saved = form.id ? await changeRole(api, form.id, name, rights) : await createRole(api, name, rights);
            setForm(null);
            setSaid(`${saved.name} saved as v${saved.version}.`);
            await read();
          }}
        />
      ) : (
        <Button aria-label="New role" onClick={() => setForm({ title: "New role", id: null, name: "", rights: [] })}>
          New role
        </Button>
      )}
    </>
  );
}
