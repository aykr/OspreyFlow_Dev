// The Admin area (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): the deployment's administration,
// inside the running system and behind the same sign-in — no separate console to start. People and
// their roles, dashboard identities, and the system's health; each tab shown only to an account
// holding its right, and the Conduit refusing anything a stale view still offers.
import { useEffect, useState } from "react";

import type { DashboardIdentity, PersonAccount, SystemStatus } from "../../../../packages/schemas/generated";
import { Button, Input, Select, Tabs } from "../design/primitives";
import {
  listDashboards,
  listPeople,
  registerDashboard,
  removeDashboard,
  setRoles,
  systemStatus,
  type AdminApi,
} from "./api";

const utc = (iso: string) => `${iso.slice(0, 16).replace("T", " ")} UTC`;

/** How fresh a dashboard's figures are, from the reporting mart (ADR-111 Amendment 2): a standing
 * failure first, in the sync service's own words; then the last good pull; else never pulled. */
export function feedFreshness(d: DashboardIdentity): { text: string; failing: boolean } {
  const cases = d.cases_pulled ?? 0;
  if (d.last_failure && d.failed_at) {
    const last = d.last_pulled ? `; last good pull ${utc(d.last_pulled)}` : "; never pulled";
    return { text: `Failing since ${utc(d.failed_at)}: ${d.last_failure}${last}`, failing: true };
  }
  if (d.last_pulled) {
    return { text: `Pulled ${utc(d.last_pulled)} · ${cases} ${cases === 1 ? "case" : "cases"}`, failing: false };
  }
  return { text: "Never pulled: no case has given it Viewer yet", failing: false };
}

export interface AdminPlaceProps extends AdminApi {
  rights: ReadonlySet<string>;
}

/** ADR-112's four roles, by the name the identity provider gives them. */
export const ROLES: { id: string; label: string }[] = [
  { id: "analyst", label: "Analyst" },
  { id: "data_engineer", label: "Data Engineer" },
  { id: "osprey-admin", label: "Admin" },
  { id: "reports_viewer", label: "Reports Viewer" },
];
const ROLE_IDS = new Set(ROLES.map((r) => r.id));

function PersonRow({ api, person, onSaved }: { api: AdminApi; person: PersonAccount; onSaved: (p: PersonAccount) => void }) {
  const [chosen, setChosen] = useState(new Set((person.roles ?? []).filter((r) => ROLE_IDS.has(r))));
  const [said, setSaid] = useState<string | null>(null);
  const others = (person.roles ?? []).filter((r) => !ROLE_IDS.has(r));
  const changed = ROLES.some((r) => chosen.has(r.id) !== (person.roles ?? []).includes(r.id));
  return (
    <tr>
      <td>
        <span className="value">{person.name}</span>
        <br />
        <span className="label">{`${person.username} · ${person.clearance ?? "no clearance"} · ${person.org_unit ?? "no unit"}`}</span>
      </td>
      {ROLES.map((role) => (
        <td key={role.id} style={{ textAlign: "center" }}>
          <input
            type="checkbox"
            aria-label={`${role.label} for ${person.username}`}
            checked={chosen.has(role.id)}
            onChange={(e) => {
              const next = new Set(chosen);
              if (e.target.checked) next.add(role.id);
              else next.delete(role.id);
              setChosen(next);
            }}
          />
        </td>
      ))}
      <td className="label">{others.length ? others.join(", ") : "—"}</td>
      <td>
        <Button
          disabled={!changed}
          aria-label={`Save roles for ${person.username}`}
          onClick={() =>
            void setRoles(api, person.id, [...ROLES.map((r) => r.id).filter((id) => chosen.has(id)), ...others])
              .then((saved) => {
                setSaid("Saved.");
                onSaved(saved);
              })
              .catch((e: Error) => setSaid(e.message))
          }
        >
          Save
        </Button>
        {said && <span role="status" className="label">{` ${said}`}</span>}
      </td>
    </tr>
  );
}

function People({ api }: { api: AdminApi }) {
  const [people, setPeople] = useState<PersonAccount[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    listPeople(api).then(setPeople).catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);
  if (problem) return <p role="alert">{problem}</p>;
  if (!people) return <p className="label">Reading the people…</p>;
  return (
    <>
      <p className="label" style={{ margin: 0 }}>
        A role grants what a person may do, never what they may see: that stays their clearance and the cases they are given.
        Other grants (single rights, older roles) are kept as they are.
      </p>
      <table className="table" aria-label="People and their roles">
        <thead>
          <tr>
            <th>Person</th>
            {ROLES.map((r) => (
              <th key={r.id} style={{ textAlign: "center" }}>{r.label}</th>
            ))}
            <th>Other grants</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {people.map((p) => (
            <PersonRow key={p.id} api={api} person={p} onSaved={(saved) => setPeople(people.map((x) => (x.id === saved.id ? saved : x)))} />
          ))}
        </tbody>
      </table>
    </>
  );
}

function Dashboards({ api }: { api: AdminApi }) {
  const [dashboards, setDashboards] = useState<DashboardIdentity[] | null>(null);
  const [levels, setLevels] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [clearance, setClearance] = useState("");
  const [unit, setUnit] = useState("");
  const [secret, setSecret] = useState<{ clientId: string; value: string } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    listDashboards(api).then(setDashboards).catch((e: Error) => setProblem(e.message));
    fetch(`${api.apiBaseUrl}/v1/handling-scheme`, { headers: { Authorization: `Bearer ${api.bearerToken}` } })
      .then((r) => (r.ok ? r.json() : { classification: [] }))
      .then((scheme: { classification?: string[] }) => {
        setLevels(scheme.classification ?? []);
        setClearance((scheme.classification ?? [])[0] ?? "");
      })
      .catch(() => setLevels([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);

  return (
    <>
      <p className="label" style={{ margin: 0 }}>
        A dashboard reads the reporting feed as an identity of its own. Register it here; a case's Author then gives its account
        Viewer on that case, as for a person. It cannot read above your own clearance.
      </p>
      {problem && <p role="alert">{problem}</p>}
      {secret && (
        <div role="status" style={{ border: "1px solid var(--warning)", padding: "var(--sp-8)" }}>
          <p style={{ margin: 0 }}>{`${secret.clientId} is registered. Its secret is shown once — copy it into the dashboard's settings now:`}</p>
          <code>{secret.value}</code>
        </div>
      )}
      <table className="table" aria-label="Dashboard identities">
        <thead>
          <tr>
            <th>Dashboard</th>
            <th>Account (give this to a case's Author)</th>
            <th>Reads at</th>
            <th>Figures</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(dashboards ?? []).map((d) => (
            <tr key={d.client_id}>
              <td>{d.client_id}</td>
              <td><code>{d.account_id}</code></td>
              <td>{`${d.clearance ?? "—"} · ${d.org_unit ?? "—"}`}</td>
              <td style={feedFreshness(d).failing ? { color: "var(--error)" } : undefined}>{feedFreshness(d).text}</td>
              <td>
                <Button
                  aria-label={`Remove ${d.client_id}`}
                  onClick={() =>
                    void removeDashboard(api, d.client_id)
                      .then(() => setDashboards((dashboards ?? []).filter((x) => x.client_id !== d.client_id)))
                      .catch((e: Error) => setProblem(e.message))
                  }
                >
                  Remove
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {dashboards?.length === 0 && <p className="label" style={{ margin: 0 }}>No dashboard is registered.</p>}
      <form
        aria-label="Register a dashboard"
        onSubmit={(e) => {
          e.preventDefault();
          setProblem(null);
          void registerDashboard(api, name.trim(), clearance, unit.trim())
            .then((made) => {
              setSecret({ clientId: made.dashboard.client_id, value: made.secret });
              setDashboards([...(dashboards ?? []), made.dashboard]);
              setName("");
            })
            .catch((err: Error) => setProblem(err.message));
        }}
        style={{ display: "grid", gap: "var(--sp-8)", maxWidth: 420, border: "1px solid var(--border-subtle)", padding: "var(--sp-12)" }}
      >
        <h3 className="value" style={{ margin: 0 }}>Register a dashboard</h3>
        <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
          Name
          <Input aria-label="Dashboard name" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
          Reads at clearance
          <Select aria-label="Dashboard clearance" value={clearance} onChange={(e) => setClearance(e.target.value)}>
            {levels.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </Select>
        </label>
        <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
          Unit
          <Input aria-label="Dashboard unit" value={unit} onChange={(e) => setUnit(e.target.value)} />
        </label>
        <Button type="submit" variant="primary" disabled={!name.trim() || !clearance || !unit.trim()}>
          Register
        </Button>
      </form>
    </>
  );
}

function System({ api }: { api: AdminApi }) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const ask = () => {
    setProblem(null);
    systemStatus(api).then(setStatus).catch((e: Error) => setProblem(e.message));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(ask, [api.apiBaseUrl, api.bearerToken]);
  return (
    <>
      {problem && <p role="alert">{problem}</p>}
      {status && (
        <ul aria-label="Components" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-8)" }}>
          {(status.components ?? []).map((c) => (
            <li key={c.name} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "baseline" }}>
              <span aria-hidden style={{ width: 10, height: 10, borderRadius: "50%", background: `var(${c.ok ? "--success" : "--error"})` }} />
              <span className="value">{c.name}</span>
              <span className="label">{c.ok ? `answered in ${c.millis} ms` : `not answering: ${c.detail ?? "no reason given"}`}</span>
            </li>
          ))}
        </ul>
      )}
      {status?.version && <p className="label" style={{ margin: 0 }}>{`Version ${status.version}`}</p>}
      <Button onClick={ask}>Ask again</Button>
    </>
  );
}

type Tab = "people" | "dashboards" | "system";

export function AdminPlace({ rights, ...api }: AdminPlaceProps) {
  const tabs = [
    ...(rights.has("manage_people") ? [{ id: "people", label: "People and roles" }] : []),
    ...(rights.has("manage_dashboards") ? [{ id: "dashboards", label: "Dashboards" }] : []),
    ...(rights.has("administer_system") ? [{ id: "system", label: "System" }] : []),
  ];
  const [tab, setTab] = useState<Tab>((tabs[0]?.id as Tab) ?? "system");
  return (
    <section aria-label="Admin" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)", padding: "var(--sp-16)", minHeight: 0, flex: 1, overflowY: "auto" }}>
      <h2 className="value" style={{ margin: 0 }}>Admin</h2>
      {tabs.length === 0 && <p className="label">Your account holds no administration right.</p>}
      {tabs.length > 0 && <Tabs tabs={tabs} activeId={tab} onChange={(id) => setTab(id as Tab)} />}
      {tab === "people" && rights.has("manage_people") && <People api={api} />}
      {tab === "dashboards" && rights.has("manage_dashboards") && <Dashboards api={api} />}
      {tab === "system" && rights.has("administer_system") && <System api={api} />}
    </section>
  );
}
