// The Admin area (`06_DECISIONS.md` ADR-110 Amendment 1, ADR-112): the deployment's administration,
// inside the running system and behind the same sign-in — no separate console to start. People and
// their roles, dashboard identities, and the system's health; each tab shown only to an account
// holding its right, and the Conduit refusing anything a stale view still offers.
import { useEffect, useState } from "react";

import type {
  DashboardIdentity,
  DemoPackStatus,
  PersonAccount,
  SignInDelivery,
  SystemStatus,
} from "../../../../packages/schemas/generated";
import { Button, Input, Select, Tabs } from "../design/primitives";
import { Schedules } from "./Schedules";
import {
  disablePerson,
  enablePerson,
  invitePerson,
  listDashboards,
  listDemoPacks,
  listPeople,
  registerDashboard,
  removeDashboard,
  resetSignIn,
  setAccess,
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

/** The deployment's classifications and handling codes, for the access a person is given. */
interface Scheme {
  levels: string[];
  codes: string[];
}

function useScheme(api: AdminApi): Scheme {
  const [scheme, setScheme] = useState<Scheme>({ levels: [], codes: [] });
  useEffect(() => {
    fetch(`${api.apiBaseUrl}/v1/handling-scheme`, { headers: { Authorization: `Bearer ${api.bearerToken}` } })
      .then((r) => (r.ok ? r.json() : {}))
      .then((body: { classification?: string[]; handling_codes?: Record<string, unknown> }) =>
        setScheme({ levels: body.classification ?? [], codes: Object.keys(body.handling_codes ?? {}) }),
      )
      .catch(() => setScheme({ levels: [], codes: [] }));
  }, [api.apiBaseUrl, api.bearerToken]);
  return scheme;
}

/** How the person signs in next (ADR-114 Amendment 5): the identity provider's emailed link, or a
 * one-time code shown here once — never stored, changed by the person at first sign-in. */
function Delivered({ delivery }: { delivery: SignInDelivery }) {
  const who = delivery.person.name || delivery.person.username;
  if (delivery.delivery === "email") {
    return (
      <p role="status" style={{ margin: 0 }}>
        {`An email with a link to set a password went to ${delivery.person.email ?? who}. They choose their own password there.`}
      </p>
    );
  }
  return (
    <div role="status" style={{ border: "1px solid var(--warning)", padding: "var(--sp-8)", display: "grid", gap: "var(--sp-4)" }}>
      <p style={{ margin: 0 }}>
        {`Give this one-time code to ${who} in person. It is shown once, here; at first sign-in they choose their own password.`}
      </p>
      <code style={{ fontSize: "var(--fs-16)" }}>{delivery.one_time_code}</code>
    </div>
  );
}

function CodeChoices({
  codes,
  chosen,
  onChange,
  label,
}: {
  codes: string[];
  chosen: Set<string>;
  onChange: (next: Set<string>) => void;
  label: (code: string) => string;
}) {
  return (
    <span style={{ display: "inline-flex", gap: "var(--sp-8)" }}>
      {codes.map((code) => (
        <label key={code} className="label" style={{ display: "inline-flex", gap: "var(--sp-4)", alignItems: "center" }}>
          <input
            type="checkbox"
            aria-label={label(code)}
            checked={chosen.has(code)}
            onChange={(e) => {
              const next = new Set(chosen);
              if (e.target.checked) next.add(code);
              else next.delete(code);
              onChange(next);
            }}
          />
          {code}
        </label>
      ))}
    </span>
  );
}

function AccessEditor({
  api,
  person,
  scheme,
  onSaved,
}: {
  api: AdminApi;
  person: PersonAccount;
  scheme: Scheme;
  onSaved: (p: PersonAccount) => void;
}) {
  const [clearance, setClearance] = useState(person.clearance ?? scheme.levels[0] ?? "");
  const [unit, setUnit] = useState(person.org_unit ?? "");
  const [codes, setCodes] = useState(new Set(person.receivable_handling_codes ?? []));
  const [said, setSaid] = useState<string | null>(null);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-12)", alignItems: "center" }}>
      <Select aria-label={`Clearance for ${person.username}`} value={clearance} onChange={(e) => setClearance(e.target.value)}>
        {scheme.levels.map((l) => (
          <option key={l} value={l}>{l}</option>
        ))}
      </Select>
      <Input aria-label={`Unit for ${person.username}`} value={unit} onChange={(e) => setUnit(e.target.value)} />
      <CodeChoices codes={scheme.codes} chosen={codes} onChange={setCodes} label={(c) => `Handling code ${c} for ${person.username}`} />
      <Button
        aria-label={`Save access for ${person.username}`}
        disabled={!clearance || !unit.trim()}
        onClick={() =>
          void setAccess(api, person.id, { clearance, org_unit: unit.trim(), receivable_handling_codes: [...codes] })
            .then((saved) => {
              setSaid("Saved.");
              onSaved(saved);
            })
            .catch((e: Error) => setSaid(e.message))
        }
      >
        Save access
      </Button>
      {said && <span role="status" className="label">{said}</span>}
    </div>
  );
}

function PersonRow({
  api,
  person,
  scheme,
  onSaved,
  onDelivered,
}: {
  api: AdminApi;
  person: PersonAccount;
  scheme: Scheme;
  onSaved: (p: PersonAccount) => void;
  onDelivered: (d: SignInDelivery) => void;
}) {
  const [chosen, setChosen] = useState(new Set((person.roles ?? []).filter((r) => ROLE_IDS.has(r))));
  const [said, setSaid] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const others = (person.roles ?? []).filter((r) => !ROLE_IDS.has(r));
  const changed = ROLES.some((r) => chosen.has(r.id) !== (person.roles ?? []).includes(r.id));
  const status = !person.enabled ? "Disabled" : person.must_set_password ? "Invited — must set a password" : null;
  const act = (done: Promise<PersonAccount>) =>
    void done
      .then((saved) => {
        setSaid(null);
        onSaved(saved);
      })
      .catch((e: Error) => setSaid(e.message));
  return (
    <>
      <tr>
        <td>
          <span className="value">{person.name}</span>
          <br />
          <span className="label">{`${person.username} · ${person.clearance ?? "no clearance"} · ${person.org_unit ?? "no unit"}`}</span>
          {status && (
            <>
              <br />
              <span className="label" style={!person.enabled ? { color: "var(--warning)" } : undefined}>{status}</span>
            </>
          )}
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
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-4)" }}>
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
            <Button aria-label={`Edit access for ${person.username}`} aria-expanded={editing} onClick={() => setEditing(!editing)}>
              Access
            </Button>
            {person.enabled ? (
              confirming ? (
                <>
                  <Button
                    aria-label={`Confirm disabling ${person.username}`}
                    onClick={() => {
                      setConfirming(false);
                      act(disablePerson(api, person.id));
                    }}
                  >
                    Confirm disable
                  </Button>
                  <Button aria-label={`Keep ${person.username} enabled`} onClick={() => setConfirming(false)}>
                    Cancel
                  </Button>
                </>
              ) : (
                <Button aria-label={`Disable ${person.username}`} onClick={() => setConfirming(true)}>
                  Disable
                </Button>
              )
            ) : (
              <Button aria-label={`Enable ${person.username}`} onClick={() => act(enablePerson(api, person.id))}>
                Enable
              </Button>
            )}
            <Button
              aria-label={`Reset sign-in for ${person.username}`}
              onClick={() =>
                void resetSignIn(api, person.id)
                  .then((delivery) => {
                    onSaved(delivery.person);
                    onDelivered(delivery);
                  })
                  .catch((e: Error) => setSaid(e.message))
              }
            >
              Reset sign-in
            </Button>
          </div>
          {said && <span role="status" className="label">{` ${said}`}</span>}
        </td>
      </tr>
      {editing && (
        <tr>
          <td colSpan={ROLES.length + 3}>
            <AccessEditor api={api} person={person} scheme={scheme} onSaved={onSaved} />
          </td>
        </tr>
      )}
    </>
  );
}

function InviteForm({
  api,
  scheme,
  onInvited,
}: {
  api: AdminApi;
  scheme: Scheme;
  onInvited: (d: SignInDelivery) => void;
}) {
  const [username, setUsername] = useState("");
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [email, setEmail] = useState("");
  const [clearance, setClearance] = useState("");
  const [unit, setUnit] = useState("");
  const [codes, setCodes] = useState(new Set<string>());
  const [roles, setRolesChosen] = useState(new Set<string>());
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    if (!clearance && scheme.levels[0]) setClearance(scheme.levels[0]);
  }, [scheme.levels, clearance]);
  const field = { display: "grid", gap: "var(--sp-4)" } as const;
  return (
    <form
      aria-label="Invite a person"
      onSubmit={(e) => {
        e.preventDefault();
        setProblem(null);
        void invitePerson(api, {
          username: username.trim(),
          first_name: first.trim(),
          last_name: last.trim(),
          email: email.trim() || null,
          clearance,
          org_unit: unit.trim(),
          receivable_handling_codes: [...codes],
          roles: ROLES.map((r) => r.id).filter((id) => roles.has(id)),
        })
          .then((delivery) => {
            onInvited(delivery);
            setUsername("");
            setFirst("");
            setLast("");
            setEmail("");
          })
          .catch((err: Error) => setProblem(err.message));
      }}
      style={{ display: "grid", gap: "var(--sp-8)", maxWidth: 520, border: "1px solid var(--border-subtle)", padding: "var(--sp-12)" }}
    >
      <h3 className="value" style={{ margin: 0 }}>Invite a person</h3>
      <p className="label" style={{ margin: 0 }}>
        They are signed in by an emailed link when this deployment has a mail server and you give an address; otherwise you
        are shown a one-time code to give them in person. Nobody can be given more than you hold.
      </p>
      {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
      <label className="label" style={field}>
        Sign-in name
        <Input aria-label="Sign-in name" value={username} onChange={(e) => setUsername(e.target.value)} />
      </label>
      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
        <label className="label" style={{ ...field, flex: 1 }}>
          First name
          <Input aria-label="First name" value={first} onChange={(e) => setFirst(e.target.value)} />
        </label>
        <label className="label" style={{ ...field, flex: 1 }}>
          Last name
          <Input aria-label="Last name" value={last} onChange={(e) => setLast(e.target.value)} />
        </label>
      </div>
      <label className="label" style={field}>
        Email (optional)
        <Input aria-label="Email (optional)" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
        <label className="label" style={{ ...field, flex: 1 }}>
          Clearance
          <Select aria-label="Invite clearance" value={clearance} onChange={(e) => setClearance(e.target.value)}>
            {scheme.levels.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </Select>
        </label>
        <label className="label" style={{ ...field, flex: 1 }}>
          Unit
          <Input aria-label="Invite unit" value={unit} onChange={(e) => setUnit(e.target.value)} />
        </label>
      </div>
      <div className="label" style={field}>
        Handling codes they may receive
        <CodeChoices codes={scheme.codes} chosen={codes} onChange={setCodes} label={(c) => `Invite with handling code ${c}`} />
      </div>
      <div className="label" style={field}>
        Roles
        <span style={{ display: "inline-flex", flexWrap: "wrap", gap: "var(--sp-8)" }}>
          {ROLES.map((role) => (
            <label key={role.id} style={{ display: "inline-flex", gap: "var(--sp-4)", alignItems: "center" }}>
              <input
                type="checkbox"
                aria-label={`Invite as ${role.label}`}
                checked={roles.has(role.id)}
                onChange={(e) => {
                  const next = new Set(roles);
                  if (e.target.checked) next.add(role.id);
                  else next.delete(role.id);
                  setRolesChosen(next);
                }}
              />
              {role.label}
            </label>
          ))}
        </span>
      </div>
      <Button type="submit" variant="primary" disabled={!username.trim() || !clearance || !unit.trim()}>
        Invite
      </Button>
    </form>
  );
}

function People({ api }: { api: AdminApi }) {
  const [people, setPeople] = useState<PersonAccount[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [delivered, setDelivered] = useState<SignInDelivery | null>(null);
  const scheme = useScheme(api);
  useEffect(() => {
    listPeople(api).then(setPeople).catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);
  if (problem) return <p role="alert">{problem}</p>;
  if (!people) return <p className="label">Reading the people…</p>;
  const saved = (p: PersonAccount) => setPeople((current) => (current ?? []).map((x) => (x.id === p.id ? p : x)));
  return (
    <>
      <p className="label" style={{ margin: 0 }}>
        A role grants what a person may do, never what they may see: that stays their clearance and the cases they are given.
        Other grants (single rights, older roles) are kept as they are.
      </p>
      {delivered && <Delivered delivery={delivered} />}
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
            <PersonRow key={p.id} api={api} person={p} scheme={scheme} onSaved={saved} onDelivered={setDelivered} />
          ))}
        </tbody>
      </table>
      <InviteForm
        api={api}
        scheme={scheme}
        onInvited={(delivery) => {
          setDelivered(delivery);
          setPeople((current) => [...(current ?? []), delivery.person]);
        }}
      />
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

/** The demo packs (ADR-114 Amendment 5, "Show and explain"): what each shows, its licence and
 * credit, whether it is loaded, and the command that adds it on the host. The Glass runs nothing. */
function DemoPacks({ api }: { api: AdminApi }) {
  const [packs, setPacks] = useState<DemoPackStatus[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [copied, setCopied] = useState<{ id: string; said: string } | null>(null);
  useEffect(() => {
    listDemoPacks(api).then(setPacks).catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);
  if (problem) return <p role="alert">{problem}</p>;
  if (!packs) return <p className="label">Reading the demo packs…</p>;
  const copy = (pack: DemoPackStatus) =>
    void Promise.resolve()
      .then(() => navigator.clipboard.writeText(pack.command))
      .then(() => setCopied({ id: pack.id, said: "Copied. Run it in a terminal on the machine OspreyFlow runs on." }))
      .catch(() => setCopied({ id: pack.id, said: "Your browser would not let the page copy; select the command and copy it." }));
  return (
    <>
      <p className="label" style={{ margin: 0 }}>
        A demo pack is added on the machine OspreyFlow runs on, with the command shown — this page never runs it. Each loads
        into a case of its own, with whoever adds it as its Author.
      </p>
      {packs.map((pack) => (
        <article
          key={pack.id}
          aria-label={pack.title}
          style={{ border: "1px solid var(--border-subtle)", padding: "var(--sp-12)", display: "grid", gap: "var(--sp-6)" }}
        >
          <h3 className="value" style={{ margin: 0 }}>{pack.title}</h3>
          <p style={{ margin: 0 }}>{pack.shows}</p>
          <p className="label" style={{ margin: 0 }}>
            {`Licence: ${pack.licence}`}
            {pack.attribution ? ` · Credit: ${pack.attribution}` : ""}
          </p>
          <p className="label" style={{ margin: 0 }}>
            {pack.loaded_case_id ? `Loaded, in “${pack.case_name}”.` : "Not in any case you can open."}
          </p>
          {pack.source_page && (
            <p className="label" style={{ margin: 0 }}>
              <a href={pack.source_page} target="_blank" rel="noreferrer">{`Download ${pack.title.split(" ")[0]}'s file`}</a>
              {pack.size_bytes ? ` (${Math.round(pack.size_bytes / 1e6)} MB), then give its path in the command.` : ""}
            </p>
          )}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)", alignItems: "center" }}>
            <code>{pack.command}</code>
            <Button aria-label={`Copy the command for ${pack.id}`} onClick={() => copy(pack)}>
              Copy
            </Button>
            {copied?.id === pack.id && <span role="status" className="label">{copied.said}</span>}
          </div>
        </article>
      ))}
    </>
  );
}

type Tab = "people" | "dashboards" | "schedules" | "system" | "demo-packs";

export function AdminPlace({ rights, ...api }: AdminPlaceProps) {
  const tabs = [
    ...(rights.has("manage_people") ? [{ id: "people", label: "People and roles" }] : []),
    ...(rights.has("manage_dashboards") ? [{ id: "dashboards", label: "Dashboards" }] : []),
    ...(rights.has("operate_schedules") ? [{ id: "schedules", label: "Schedules and runs" }] : []),
    ...(rights.has("administer_system") ? [{ id: "system", label: "System" }] : []),
    ...(rights.has("administer_system") ? [{ id: "demo-packs", label: "Demo packs" }] : []),
  ];
  const [tab, setTab] = useState<Tab>((tabs[0]?.id as Tab) ?? "system");
  return (
    <section aria-label="Admin" style={{ display: "flex", flexDirection: "column", gap: "var(--sp-12)", padding: "var(--sp-16)", minHeight: 0, flex: 1, overflowY: "auto" }}>
      <h2 className="value" style={{ margin: 0 }}>Admin</h2>
      {tabs.length === 0 && <p className="label">Your account holds no administration right.</p>}
      {tabs.length > 0 && <Tabs tabs={tabs} activeId={tab} onChange={(id) => setTab(id as Tab)} />}
      {tab === "people" && rights.has("manage_people") && <People api={api} />}
      {tab === "dashboards" && rights.has("manage_dashboards") && <Dashboards api={api} />}
      {tab === "schedules" && rights.has("operate_schedules") && <Schedules api={api} />}
      {tab === "system" && rights.has("administer_system") && <System api={api} />}
      {tab === "demo-packs" && rights.has("administer_system") && <DemoPacks api={api} />}
    </section>
  );
}
