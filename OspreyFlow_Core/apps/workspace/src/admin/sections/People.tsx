// Admin › People › People and roles (ADR-110 Amendment 1, ADR-112, ADR-114 Amendment 5; ADR-145
// decision 5): each person's roles, access and state, inviting a person, and refused organisation
// sign-ins. Behind `manage_people` (`admin/sections.json`).
import { useEffect, useState } from "react";

import type { OrganisationArrival, PersonAccount, SignInDelivery } from "../../../../../packages/schemas/generated";
import { Button, Input, Select } from "../../design/primitives";
import {
  disablePerson,
  enablePerson,
  invitePerson,
  linkOrganisation,
  listArrivals,
  listPeople,
  removePerson,
  resetSignIn,
  setAccess,
  setRoles,
  type AdminApi,
} from "../api";

const utc = (iso: string) => `${iso.slice(0, 16).replace("T", " ")} UTC`;

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

/** ADR-112 Amendment 3: what removing a person does, said before it is done. */
export function removalWords(person: PersonAccount): string {
  const who = person.name && person.name !== person.username ? `${person.name} (${person.username})` : person.username;
  return (
    `Remove ${who}? Their account is deleted: they can no longer sign in, and their sign-in name and email address ` +
    "become free to use again. Cases, alerts and recipes they made stay as they are and show their id in place of " +
    "their name. This cannot be undone. To keep the account but stop them signing in, disable it instead."
  );
}

function RemoveConfirmation({
  api,
  person,
  onRemoved,
  onCancel,
}: {
  api: AdminApi;
  person: PersonAccount;
  onRemoved: (p: PersonAccount) => void;
  onCancel: () => void;
}) {
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <div
      role="group"
      aria-label={`Remove ${person.username}`}
      style={{ border: "1px solid var(--warning)", padding: "var(--sp-8)", display: "grid", gap: "var(--sp-8)" }}
    >
      <p style={{ margin: 0 }}>{removalWords(person)}</p>
      {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
        <Button
          aria-label={`Confirm removing ${person.username}`}
          onClick={() =>
            void removePerson(api, person.id)
              .then(onRemoved)
              .catch((e: Error) => setProblem(e.message))
          }
        >
          Remove the account
        </Button>
        <Button aria-label={`Keep ${person.username}`} onClick={onCancel}>
          Keep it
        </Button>
      </div>
    </div>
  );
}

function PersonRow({
  api,
  person,
  scheme,
  onSaved,
  onDelivered,
  onRemoved,
}: {
  api: AdminApi;
  person: PersonAccount;
  scheme: Scheme;
  onSaved: (p: PersonAccount) => void;
  onDelivered: (d: SignInDelivery) => void;
  onRemoved: (p: PersonAccount) => void;
}) {
  const [chosen, setChosen] = useState(new Set((person.roles ?? []).filter((r) => ROLE_IDS.has(r))));
  const [said, setSaid] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [removing, setRemoving] = useState(false);
  const others = (person.roles ?? []).filter((r) => !ROLE_IDS.has(r));
  const changed = ROLES.some((r) => chosen.has(r.id) !== (person.roles ?? []).includes(r.id));
  const status = !person.enabled ? "Disabled" : person.must_set_password ? "Invited — must set a password" : null;
  const joined = person.organisation_linked ? "Signs in through the organisation" : null;
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
          {joined && (
            <>
              <br />
              <span className="label">{joined}</span>
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
            {!person.system_account && (
              <Button aria-label={`Remove ${person.username}`} aria-expanded={removing} onClick={() => setRemoving(!removing)}>
                Remove
              </Button>
            )}
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
      {removing && (
        <tr>
          <td colSpan={ROLES.length + 3}>
            <RemoveConfirmation api={api} person={person} onRemoved={onRemoved} onCancel={() => setRemoving(false)} />
          </td>
        </tr>
      )}
    </>
  );
}

/** ADR-112 Amendment 3 (b): what joining does, said before it is done. */
export function joinWords(arrival: OrganisationArrival, person: PersonAccount): string {
  const them = arrival.provider_username || "this organisation account";
  const who = person.name && person.name !== person.username ? `${person.name} (${person.username})` : person.username;
  return (
    `Join ${them} to ${who}? From their next sign-in through the organisation they land in ${person.username}'s ` +
    "account, with its roles, clearance and cases. Do this only if you are sure they are the same person: the " +
    "organisation said only that its account carries the same email address."
  );
}

function ArrivalRow({
  api,
  arrival,
  people,
  onJoined,
}: {
  api: AdminApi;
  arrival: OrganisationArrival;
  people: PersonAccount[];
  onJoined: (arrival: OrganisationArrival, person: PersonAccount) => void;
}) {
  const them = arrival.provider_username || "(no name given)";
  const eligible = people.filter((p) => !p.system_account && !p.organisation_linked);
  const [target, setTarget] = useState(eligible[0]?.id ?? "");
  const [confirming, setConfirming] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const chosen = eligible.find((p) => p.id === target);
  return (
    <tr>
      <td>
        <span className="value">{them}</span>
        <br />
        <span className="label">
          {`Refused ${arrival.attempts} ${arrival.attempts === 1 ? "time" : "times"}, last at ${utc(arrival.last_refused)}`}
        </span>
      </td>
      <td>
        <div style={{ display: "grid", gap: "var(--sp-8)" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)", alignItems: "center" }}>
            <Select aria-label={`Account to join ${them} to`} value={target} onChange={(e) => setTarget(e.target.value)}>
              {eligible.map((p) => (
                <option key={p.id} value={p.id}>{`${p.name} (${p.username})`}</option>
              ))}
            </Select>
            <Button
              aria-label={`Join ${them}`}
              aria-expanded={confirming}
              disabled={!chosen}
              onClick={() => setConfirming(!confirming)}
            >
              Join
            </Button>
          </div>
          {confirming && chosen && (
            <div
              role="group"
              aria-label={`Join ${them}`}
              style={{ border: "1px solid var(--warning)", padding: "var(--sp-8)", display: "grid", gap: "var(--sp-8)" }}
            >
              <p style={{ margin: 0 }}>{joinWords(arrival, chosen)}</p>
              {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
              <div style={{ display: "flex", gap: "var(--sp-8)" }}>
                <Button
                  aria-label={`Confirm joining ${them}`}
                  onClick={() =>
                    void linkOrganisation(api, chosen.id, arrival.subject)
                      .then((person) => onJoined(arrival, person))
                      .catch((e: Error) => setProblem(e.message))
                  }
                >
                  Join the accounts
                </Button>
                <Button aria-label={`Do not join ${them}`} onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

/** ADR-112 Amendment 3 (b): people the organisation's sign-in refused because an OspreyFlow
 * account holds their email address, each offered for joining to an account. */
function Arrivals({
  api,
  arrivals,
  people,
  onJoined,
}: {
  api: AdminApi;
  arrivals: OrganisationArrival[];
  people: PersonAccount[];
  onJoined: (arrival: OrganisationArrival, person: PersonAccount) => void;
}) {
  if (!arrivals.length) return null;
  return (
    <section aria-label="Refused organisation sign-ins" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 className="value" style={{ margin: 0 }}>Refused organisation sign-ins</h3>
      <p className="label" style={{ margin: 0 }}>
        These people signed in through the organisation and were refused, because an OspreyFlow account already holds
        their email address. Join one to the account that is theirs, or remove that account so they arrive afresh.
        The identity provider keeps this list for seven days.
      </p>
      <table className="table" aria-label="Refused organisation sign-ins">
        <thead>
          <tr>
            <th>Organisation account</th>
            <th>Join to</th>
          </tr>
        </thead>
        <tbody>
          {arrivals.map((a) => (
            <ArrivalRow key={a.subject} api={api} arrival={a} people={people} onJoined={onJoined} />
          ))}
        </tbody>
      </table>
    </section>
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

export function People({ api }: { api: AdminApi }) {
  const [people, setPeople] = useState<PersonAccount[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [delivered, setDelivered] = useState<SignInDelivery | null>(null);
  const [removed, setRemoved] = useState<PersonAccount | null>(null);
  const [arrivals, setArrivals] = useState<OrganisationArrival[]>([]);
  const [arrivalsProblem, setArrivalsProblem] = useState<string | null>(null);
  const [joined, setJoined] = useState<string | null>(null);
  const scheme = useScheme(api);
  useEffect(() => {
    listPeople(api).then(setPeople).catch((e: Error) => setProblem(e.message));
    listArrivals(api).then(setArrivals).catch((e: Error) => setArrivalsProblem(e.message));
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
      {joined && (
        <p role="status" style={{ margin: 0 }}>
          {joined}
        </p>
      )}
      {arrivalsProblem && <p role="alert" style={{ margin: 0 }}>{`Refused organisation sign-ins could not be read: ${arrivalsProblem}`}</p>}
      <Arrivals
        api={api}
        arrivals={arrivals}
        people={people}
        onJoined={(arrival, person) => {
          saved(person);
          setArrivals((current) => current.filter((a) => a.subject !== arrival.subject));
          setJoined(
            `${arrival.provider_username || "The organisation account"} is joined to ${person.username}. Their next sign-in ` +
              "through the organisation lands in that account, with its roles.",
          );
        }}
      />
      {removed && (
        <p role="status" style={{ margin: 0 }}>
          {`${removed.name || removed.username} (${removed.username}) was removed. What they made now shows their id in place of their name.`}
        </p>
      )}
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
            <PersonRow
              key={p.id}
              api={api}
              person={p}
              scheme={scheme}
              onSaved={saved}
              onDelivered={setDelivered}
              onRemoved={(gone) => {
                setRemoved(gone);
                setPeople((current) => (current ?? []).filter((x) => x.id !== gone.id));
              }}
            />
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
