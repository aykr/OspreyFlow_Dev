// Admin › People › People and roles (ADR-110 Amendment 1, ADR-112, ADR-114 Amendment 5; ADR-145
// decisions 5 and 6 and Amendment 5): each person's roles (built-in, the Super user preset, custom),
// the places they open, their case levels (R3), access and state; the cases with no Author and
// *Name an Author* (R1); *Disable…* with a transfer for everything they own (A4); inviting a person,
// and refused organisation sign-ins. Behind `manage_people` (`admin/sections.json`).
import { useEffect, useState } from "react";

import type {
  AdminPeopleRows,
  CustomRole,
  DisablePlan,
  OrganisationArrival,
  PersonAccount,
  PersonCaseLevel,
  SignInDelivery,
} from "../../../../../packages/schemas/generated";
import { currentBrand } from "../../brand/brand";
import { PLACE_NAME, placesFor } from "../../shell/places";
import { LEVELS_TIP_ID, RoleAndLevelTips, grantWords, roleTip, roleTipId } from "../tips";
import { Button, Input, Select } from "../../design/primitives";
import {
  disablePlan,
  enablePerson,
  addPersonByObjectId,
  invitePerson,
  linkOrganisation,
  listArrivals,
  listPeople,
  signInKind,
  guestSignIn,
  setGuestSignIn,
  listRoles,
  nameAnAuthor,
  peopleRows,
  personOwnership,
  removePerson,
  resetSignIn,
  setAccess,
  setRoles,
  transferAndDisable,
  type AdminApi,
} from "../api";

const utc = (iso: string) => `${iso.slice(0, 16).replace("T", " ")} UTC`;

/** The built-in roles, by the name the identity provider gives them: ADR-112's four and Amendment 5's
 * Rule author. */
export const ROLES: { id: string; label: string }[] = [
  { id: "analyst", label: "Analyst" },
  { id: "data_engineer", label: "Data Engineer" },
  { id: "osprey-admin", label: "Admin" },
  { id: "reports_viewer", label: "Reports Viewer" },
  { id: "rule_author", label: "Rule author" },
];
const ROLE_IDS = new Set(ROLES.map((r) => r.id));
/** The Super user preset (ADR-145 Amendment 5 point 2): three roles given together, never one. */
export const SUPER_USER = ["analyst", "data_engineer", "rule_author"];

/** What the People rows need besides the people: the custom roles, the built-in roles' rights and
 * the case levels, read once for the section. */
interface Context {
  custom: CustomRole[];
  builtIn: Record<string, string[]>;
  rows: AdminPeopleRows | null;
}

/** "Author of Kestrel, Harrier; Editor of Heron through Intel" (R3). */
export function levelWords(levels: PersonCaseLevel[]): string {
  const order = ["author", "editor", "viewer"] as const;
  const said = order
    .map((level) => {
      const held = levels.filter((l) => l.level === level);
      if (!held.length) return null;
      const name = level.charAt(0).toUpperCase() + level.slice(1);
      return `${name} of ${held.map((l) => (l.through ? `${l.name} through ${l.through}` : l.name)).join(", ")}`;
    })
    .filter(Boolean);
  return said.length ? said.join("; ") : "No case levels";
}

/** The places a person's roles open (ADR-145 decision 1), from the roles' rights as the Conduit gives
 * them; a custom role by its current version. */
export function placesWords(roles: string[], ctx: Context): string {
  const rights = new Set<string>();
  for (const role of roles) {
    for (const r of ctx.builtIn[role] ?? []) rights.add(r);
    if (role.startsWith("right:")) rights.add(role.slice("right:".length));
    const custom = ctx.custom.find((c) => `role:${c.id}` === role);
    for (const r of custom?.rights ?? []) rights.add(r);
  }
  const places = placesFor(rights);
  return places.length ? `Opens ${places.map((p) => PLACE_NAME[p]).join(", ")}` : "Opens no place";
}

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

/** The three values Access sets. On Entra ID only those the deployment sets itself are offered
 * (ADR-148 Amendment 15); the others are Entra's, shown and sent back as they are. */
export type AccessField = "clearance" | "org_unit" | "handling_codes";
const EVERY_FIELD: readonly AccessField[] = ["clearance", "org_unit", "handling_codes"];

function AccessEditor({
  api,
  person,
  scheme,
  onSaved,
  fields = EVERY_FIELD,
}: {
  api: AdminApi;
  person: PersonAccount;
  scheme: Scheme;
  onSaved: (p: PersonAccount) => void;
  fields?: readonly AccessField[];
}) {
  const sets = (f: AccessField) => fields.includes(f);
  const [clearance, setClearance] = useState(person.clearance ?? scheme.levels[0] ?? "");
  const [unit, setUnit] = useState(person.org_unit ?? "");
  const [codes, setCodes] = useState(new Set(person.receivable_handling_codes ?? []));
  const [said, setSaid] = useState<string | null>(null);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-12)", alignItems: "center" }}>
      {sets("clearance") ? (
        <Select aria-label={`Clearance for ${person.username}`} value={clearance} onChange={(e) => setClearance(e.target.value)}>
          {scheme.levels.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </Select>
      ) : (
        <span className="label">Clearance {person.clearance ?? "none"}, from Entra ID</span>
      )}
      {sets("org_unit") ? (
        <Input aria-label={`Unit for ${person.username}`} value={unit} onChange={(e) => setUnit(e.target.value)} />
      ) : (
        <span className="label">Unit {person.org_unit ?? "none"}, from Entra ID</span>
      )}
      {sets("handling_codes") ? (
        <CodeChoices codes={scheme.codes} chosen={codes} onChange={setCodes} label={(c) => `Handling code ${c} for ${person.username}`} />
      ) : (
        <span className="label">Handling codes {(person.receivable_handling_codes ?? []).join(", ") || "none"}, from Entra ID</span>
      )}
      <Button
        aria-label={`Save access for ${person.username}`}
        disabled={(sets("clearance") && !clearance) || (sets("org_unit") && !unit.trim())}
        onClick={() =>
          // ADR-148 Amendment 15: only the values set here; Entra's are not given, so never changed or checked.
          void setAccess(api, person.id, {
            ...(sets("clearance") ? { clearance } : {}),
            ...(sets("org_unit") ? { org_unit: unit.trim() } : {}),
            ...(sets("handling_codes") ? { receivable_handling_codes: [...codes] } : {}),
          })
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

/** *Disable…* (ADR-145 decision 6, A4): everything the person owns, each with *Transfer to…*;
 * *Transfer and disable* is the Conduit's to refuse, in its words, while any item has no recipient. */
/** Whether a clearance clears a marking, by the scheme's order; an unknown one clears nothing. */
export function clearsMarking(levels: string[], clearance: string | null | undefined, marking: string): boolean {
  const held = clearance ? levels.indexOf(clearance) : -1;
  const needed = levels.indexOf(marking);
  return held >= 0 && needed >= 0 && held >= needed;
}

function DisablePanel({
  api,
  person,
  people,
  levels,
  onDone,
  onCancel,
}: {
  api: AdminApi;
  person: PersonAccount;
  people: PersonAccount[];
  levels: string[];
  onDone: (p: PersonAccount) => void;
  onCancel: () => void;
}) {
  const [plan, setPlan] = useState<DisablePlan | null>(null);
  const [to, setTo] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState<string | null>(null);
  // ADR-145 Amendment 8: L3.8's ownership read says whether anything is withheld from this
  // administrator, never what; the plan already offers every item they may see.
  // `null` when the read failed: the screen says it could not check, never that nothing blocks.
  const [withheld, setWithheld] = useState<boolean | null>(false);
  const read = () => {
    disablePlan(api, person.id).then(setPlan).catch((e: Error) => setProblem(e.message));
    personOwnership(api, person.id)
      .then((o) => setWithheld(o.withheld ?? false))
      .catch(() => setWithheld(null));
  };
  useEffect(read, [api, person.id]);
  const who = person.username;
  const others = people.filter((p) => p.id !== person.id && p.enabled && !p.system_account);
  const key = (kind: string, id: string) => `${kind}:${id}`;
  return (
    <div role="group" aria-label={`Disable ${who}`} style={{ display: "grid", gap: "var(--sp-8)", border: "1px solid var(--line)", padding: "var(--sp-8)" }}>
      {problem && (
        <div role="alert" style={{ border: "2px solid var(--danger)", padding: "var(--sp-8)" }}>
          <p style={{ margin: 0 }}>{`There is a problem: ${problem}`}</p>
        </div>
      )}
      {!plan ? (
        problem ? (
          <Button aria-label={`Cancel disabling ${who}`} onClick={onCancel}>
            Cancel
          </Button>
        ) : (
          <p className="label">Reading what they own…</p>
        )
      ) : (
        <>
          <p style={{ margin: 0 }}>
            {plan.items.length
              ? `${who} answers for ${plan.items.length} ${plan.items.length === 1 ? "thing" : "things"}. Choose who takes each one: nothing is deleted, and every transfer is audited.`
              : `${who} answers for nothing listed here.`}
          </p>
          {plan.items.map((item) => (
            <label key={key(item.kind, item.id)} className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
              {item.label}
              <Select
                aria-label={`Transfer to, for ${item.label}`}
                value={to[key(item.kind, item.id)] ?? ""}
                onChange={(e) => setTo({ ...to, [key(item.kind, item.id)]: e.target.value })}
              >
                <option value="">Transfer to…</option>
                {/* ADR-145 Amendment 9: only someone cleared to what the item needs is offered;
                    the Conduit refuses anyone else in the same words, naming nothing. */}
                {others
                  .filter((p) => !item.needs_clearance || clearsMarking(levels, p.clearance, item.needs_clearance))
                  .map((p) => (
                  <option key={p.id} value={p.id}>
                    {`${p.name} (${p.username})`}
                  </option>
                ))}
              </Select>
            </label>
          ))}
          {withheld === null ? (
            <p role="note" aria-label={`Items of ${who} you may not see`} style={{ margin: 0 }}>
              {`Could not check whether ${who} owns items you may not see. If they do, the disable is refused once the transfers you choose here are made.`}
            </p>
          ) : null}
          {withheld ? (
            <p role="note" aria-label={`Items of ${who} you may not see`} style={{ margin: 0 }}>
              {`${who} also owns items you may not see. The transfers you choose here go through, but ${who} stays enabled until an administrator who may see those items, or an Author of their case, transfers them.`}
            </p>
          ) : null}
          {plan.not_yet_listed?.length ? (
            <p className="label" style={{ margin: 0 }}>{`Not listed here yet: ${plan.not_yet_listed.join(", ")}.`}</p>
          ) : null}
          <div style={{ display: "flex", gap: "var(--sp-8)" }}>
            <Button
              aria-label={plan.items.length ? `Transfer and disable ${who}` : `Confirm disabling ${who}`}
              onClick={() => {
                setProblem(null);
                const transfers = plan.items
                  .filter((i) => to[key(i.kind, i.id)])
                  .map((i) => ({ kind: i.kind, id: i.id, to: to[key(i.kind, i.id)] ?? "" }));
                void transferAndDisable(api, person.id, transfers)
                  .then(onDone)
                  .catch((e: Error) => {
                    setProblem(e.message);
                    // A refusal after the transfers (another unit's items, or withheld ones) leaves
                    // those transfers standing: read the plan again, so they are not offered twice.
                    setTo({});
                    read();
                  });
              }}
            >
              {plan.items.length ? "Transfer and disable" : "Confirm disabling"}
            </Button>
            <Button aria-label={`Cancel disabling ${who}`} onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

function PersonRow({
  api,
  person,
  people,
  scheme,
  ctx,
  onSaved,
  onDelivered,
  onRemoved,
  entra = false,
  administratorSets = [],
}: {
  api: AdminApi;
  person: PersonAccount;
  people: PersonAccount[];
  scheme: Scheme;
  ctx: Context;
  onSaved: (p: PersonAccount) => void;
  onDelivered: (d: SignInDelivery) => void;
  onRemoved: (p: PersonAccount) => void;
  /** Entra ID holds the account: access, sign-in and removal are Entra's, not offered here. */
  entra?: boolean;
  /** On Entra ID, the values this deployment sets itself (ADR-148 Amendment 15): Access offers those. */
  administratorSets?: readonly AccessField[];
}) {
  const customIds = new Set(ctx.custom.map((c) => `role:${c.id}`));
  const [chosen, setChosen] = useState(
    new Set((person.roles ?? []).filter((r) => ROLE_IDS.has(r) || customIds.has(r))),
  );
  const [said, setSaid] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [removing, setRemoving] = useState(false);
  const others = (person.roles ?? []).filter((r) => !ROLE_IDS.has(r) && !customIds.has(r));
  const offered = [...ROLES.map((r) => r.id), ...customIds];
  const changed = offered.some((id) => chosen.has(id) !== (person.roles ?? []).includes(id));
  const levels = ctx.rows?.rows.find((r) => r.id === person.id)?.levels ?? [];
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
          <span className="admin-person__name" data-person-name>{person.name}</span>
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
          {person.guest && (
            <>
              <br />
              <span className="label">{GUEST_WORDS}</span>
            </>
          )}
          {!person.system_account && (
            <>
              <br />
              <span className="label">{placesWords(person.roles ?? [], ctx)}</span>
              <br />
              <span className="label" aria-describedby={LEVELS_TIP_ID}>{levelWords(levels)}</span>
            </>
          )}
        </td>
        {ROLES.map((role) => (
          <td key={role.id} style={{ textAlign: "center" }}>
            <input
              type="checkbox"
              aria-label={`${role.label} for ${person.username}`}
              aria-describedby={roleTip(role.id) ? roleTipId(role.id) : undefined}
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
        <td className="label">
          {ctx.custom.map((c) => (
            <label key={c.id} style={{ display: "block" }}>
              <input
                type="checkbox"
                aria-label={`${c.name} for ${person.username}`}
                checked={chosen.has(`role:${c.id}`)}
                onChange={(e) => {
                  const next = new Set(chosen);
                  if (e.target.checked) next.add(`role:${c.id}`);
                  else next.delete(`role:${c.id}`);
                  setChosen(next);
                }}
              />{" "}
              {c.team ? `${c.name} (team)` : c.name}
            </label>
          ))}
          {others.length ? others.map(grantWords).join(", ") : ctx.custom.length ? null : "—"}
        </td>
      </tr>
      <tr className="admin-row-actions-row">
        <td className="admin-row-actions" colSpan={ROLES.length + 2}>
          {/* The row's actions beneath it, the full width: one primary, then the rest as links (the
              GOV.UK pass, 14 Nov). */}
          <div className="admin-row-actions__line">
            <Button
              className="admin-row-actions__primary"
              disabled={!changed}
              aria-label={`Save roles for ${person.username}`}
              onClick={() =>
                void setRoles(api, person.id, [...offered.filter((id) => chosen.has(id)), ...others])
                  .then((saved) => {
                    setSaid("Saved.");
                    onSaved(saved);
                  })
                  .catch((e: Error) => setSaid(e.message))
              }
            >
              Save
            </Button>
            <div className="admin-row-actions__more">
              <button
                type="button"
                className={rowLinkClass()}
                aria-label={`Super user preset for ${person.username}`}
                onClick={() => setChosen(new Set([...[...chosen].filter((r) => !ROLE_IDS.has(r)), ...SUPER_USER]))}
              >
                Super user
              </button>
              {(!entra || administratorSets.length > 0) && (
                <button type="button" className={rowLinkClass()} aria-label={`Edit access for ${person.username}`} aria-expanded={editing} onClick={() => setEditing(!editing)}>
                  Access
                </button>
              )}
              {person.enabled ? (
                <button type="button" className={rowLinkClass()} aria-label={`Disable ${person.username}`} aria-expanded={confirming} onClick={() => setConfirming(!confirming)}>
                  Disable…
                </button>
              ) : (
                <button type="button" className={rowLinkClass()} aria-label={`Enable ${person.username}`} onClick={() => act(enablePerson(api, person.id))}>
                  Enable
                </button>
              )}
              {!entra && (
                <button
                  type="button"
                  className={rowLinkClass()}
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
                </button>
              )}
              {!entra && !person.system_account && (
                <button type="button" className={rowLinkClass()} aria-label={`Remove ${person.username}`} aria-expanded={removing} onClick={() => setRemoving(!removing)}>
                  Remove
                </button>
              )}
            </div>
            {said && <span role="status" className="label">{` ${said}`}</span>}
          </div>
        </td>
      </tr>
      {editing && (
        <tr>
          <td colSpan={ROLES.length + 2}>
            <AccessEditor
              api={api}
              person={person}
              scheme={scheme}
              onSaved={onSaved}
              fields={entra ? administratorSets : EVERY_FIELD}
            />
          </td>
        </tr>
      )}
      {confirming && person.enabled && (
        <tr>
          <td colSpan={ROLES.length + 2}>
            <DisablePanel
              api={api}
              person={person}
              people={people}
              levels={scheme.levels}
              onCancel={() => setConfirming(false)}
              onDone={(saved) => {
                setConfirming(false);
                setSaid(null);
                onSaved(saved);
              }}
            />
          </td>
        </tr>
      )}
      {removing && (
        <tr>
          <td colSpan={ROLES.length + 2}>
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
      <h2 className="value" style={{ margin: 0 }}>Refused organisation sign-ins</h2>
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

/** A person's row links: link-styled buttons, with GOV.UK's own link class (and so its focus) under that brand
 * (ADR-145 Amendment 16). */
function rowLinkClass(): string {
  return currentBrand() === "govuk" ? "admin-row-actions__link govuk-link" : "admin-row-actions__link";
}

/** ADR-148 Amendment 8: Entra ID holds the accounts. */
export const ENTRA_PEOPLE_WORDS =
  "People sign in with their organisation's Entra ID account; their clearance, unit and handling codes come " +
  "from Entra. Here you give them roles, add them by object id before they first sign in, and disable them.";

const FIELD_WORDS: Record<AccessField, string> = { clearance: "clearance", org_unit: "unit", handling_codes: "handling codes" };

/** "clearance", "clearance and unit", "clearance, unit and handling codes", in `EVERY_FIELD`'s order whatever order
 * the Conduit serves them in. */
function fieldList(fields: readonly AccessField[]): string {
  const ws = EVERY_FIELD.filter((f) => fields.includes(f)).map((f) => FIELD_WORDS[f]);
  return ws.length > 1 ? `${ws.slice(0, -1).join(", ")} and ${ws[ws.length - 1]}` : (ws[0] ?? "");
}

/** Whether the listed values take a plural verb: more than one, or handling codes alone (a plural noun). */
function plural(fields: readonly AccessField[]): boolean {
  return fields.length > 1 || fields[0] === "handling_codes";
}

/** ADR-148 Amendment 15: on the proof of concept, the values this deployment sets itself, said in words; a person
 * with none set cannot sign in until it is. */
export function entraPeopleWords(administratorSets: readonly AccessField[]): string {
  if (administratorSets.length === 0) return ENTRA_PEOPLE_WORDS;
  const many = plural(administratorSets);
  return (
    `People sign in with their organisation's Entra ID account. Their ${fieldList(administratorSets)} ` +
    `${many ? "are" : "is"} set here, with Access (none above your own), and they cannot sign in until ` +
    `${many ? "those are" : "it is"} set; anything else comes from Entra. Here you also give them roles, add them by ` +
    "object id before they first sign in, and disable them."
  );
}

/** ADR-148 Amendment 17, with Amendment 15: what an admitted guest's values come from. A guest signs in as anyone
 * does, so a value this deployment sets itself comes from People, with Access, and the rest from their token. */
export function guestAdmissionWords(administratorSets: readonly AccessField[]): string {
  const here = EVERY_FIELD.filter((f) => administratorSets.includes(f));
  const token = EVERY_FIELD.filter((f) => !administratorSets.includes(f));
  const many = plural(here);
  const parts = [
    ...(here.length
      ? [`their ${fieldList(here)} set here with Access, as anyone's ${many ? "are" : "is"}, and they cannot sign in ` +
          `until ${many ? "those are" : "it is"} set`]
      : []),
    ...(token.length ? [`${here.length ? "their" : "the same"} ${fieldList(token)} from their token`] : []),
  ];
  return (
    "A guest account is homed outside your organisation's Entra ID (another organisation's, or another identity " +
    `provider) and invited into yours. Admitted, a guest signs in as anyone does: ${parts.join("; ")}` +
    `${here.length ? ";" : ","} and the roles you give them here.`
  );
}

/** ADR-148 Amendment 17: how a guest (B2B) account is marked in the list. */
export const GUEST_WORDS = "Guest: homed outside this organisation's Entra ID; signs in only while guest accounts are admitted";

/** ADR-148 Amendment 17: whether guest (B2B) accounts may sign in, off until an administrator of people turns it on.
 * Admitted, a guest signs in as anyone does (`guestAdmissionWords`); turned off, a guest already here is refused at
 * their next request. */
function GuestsForm({ api, administratorSets }: { api: AdminApi; administratorSets: readonly AccessField[] }) {
  const [admitted, setAdmitted] = useState<boolean | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    void guestSignIn(api)
      .then((g) => setAdmitted(g.admitted))
      .catch((e: Error) => setProblem(e.message));
  }, [api]);
  return (
    <form aria-label="Guests" style={{ display: "grid", gap: "var(--sp-8)", maxWidth: "32rem" }} onSubmit={(e) => e.preventDefault()}>
      <h2 className="value" style={{ margin: 0 }}>Guests</h2>
      <p className="label" style={{ margin: 0 }}>
        {guestAdmissionWords(administratorSets)}
      </p>
      <label className="label" style={{ display: "inline-flex", gap: "var(--sp-4)", alignItems: "center" }}>
        <input
          type="checkbox"
          aria-label="Admit guest accounts"
          checked={admitted === true}
          disabled={admitted === null}
          onChange={(e) => {
            const next = e.target.checked;
            void setGuestSignIn(api, next)
              .then((g) => {
                setProblem(null);
                setAdmitted(g.admitted);
              })
              .catch((err: Error) => setProblem(err.message));
          }}
        />
        Admit guest accounts
      </label>
      {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
    </form>
  );
}

/** A person added by their Entra object id (the Entra admin centre shows it) ahead of their first sign-in, with no roles.
 * The Conduit checks the id and refuses one already here. */
function AddByObjectIdForm({ api, onAdded }: { api: AdminApi; onAdded: (p: PersonAccount) => void }) {
  const [objectId, setObjectId] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <form
      aria-label="Add a person by object id"
      style={{ display: "grid", gap: "var(--sp-8)", maxWidth: "32rem" }}
      onSubmit={(event) => {
        event.preventDefault();
        void addPersonByObjectId(api, objectId.trim())
          .then((added) => {
            setProblem(null);
            setObjectId("");
            onAdded(added);
          })
          .catch((e: Error) => setProblem(e.message));
      }}
    >
      <h2 className="value" style={{ margin: 0 }}>Add a person by object id</h2>
      <p className="label" style={{ margin: 0 }}>
        Their Entra object id, from the Entra admin centre. They are added with no roles; give them roles below,
        and they hold them from their first sign-in.
      </p>
      <Input aria-label="Entra object id" value={objectId} onChange={(event) => setObjectId(event.target.value)} />
      <div>
        <Button type="submit" disabled={!objectId.trim()}>
          Add
        </Button>
      </div>
      {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
    </form>
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
      <h2 className="value" style={{ margin: 0 }}>Invite a person</h2>
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

/** R1: the cases of your unit no enabled person is Author of, each with *Name an Author*
 * (`PUT /v1/admin/cases/{id}/authors/{account}`), which refuses a case that has an Author. */
function WithoutAuthor({
  api,
  rows,
  people,
  onNamed,
}: {
  api: AdminApi;
  rows: AdminPeopleRows;
  people: PersonAccount[];
  onNamed: () => void;
}) {
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [said, setSaid] = useState<string | null>(null);
  if (!rows.without_author.length) return null;
  const candidates = people.filter((p) => p.enabled && !p.system_account);
  return (
    <section aria-label="Cases with no Author" role="note" style={{ border: "1px solid var(--warning)", padding: "var(--sp-8)", display: "grid", gap: "var(--sp-8)" }}>
      <p style={{ margin: 0 }}>
        {`${rows.without_author.length === 1 ? "A case" : `${rows.without_author.length} cases`} of your unit ${rows.without_author.length === 1 ? "has" : "have"} no Author: nobody can share ${rows.without_author.length === 1 ? "it" : "them"}, or answer for ${rows.without_author.length === 1 ? "it" : "them"}.`}
      </p>
      {rows.without_author.map((c) => (
        <div key={c.investigation_id} style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)", alignItems: "end" }}>
          <span className="admin-case__name" data-case-name>{c.name}</span>
          <Select
            aria-label={`Author for ${c.name}`}
            value={chosen[c.investigation_id] ?? ""}
            onChange={(e) => setChosen({ ...chosen, [c.investigation_id]: e.target.value })}
          >
            <option value="">Choose a person</option>
            {candidates.map((p) => (
              <option key={p.id} value={p.id}>
                {`${p.name} (${p.username})`}
              </option>
            ))}
          </Select>
          <Button
            aria-label={`Name an Author of ${c.name}`}
            disabled={!chosen[c.investigation_id]}
            onClick={() =>
              void nameAnAuthor(api, c.investigation_id, chosen[c.investigation_id] ?? "")
                .then(() => {
                  setSaid(`${people.find((p) => p.id === chosen[c.investigation_id])?.name ?? "They"} is now an Author of ${c.name}.`);
                  onNamed();
                })
                .catch((e: Error) => setSaid(e.message))
            }
          >
            Name an Author
          </Button>
        </div>
      ))}
      {said && (
        <p role="status" className="label" style={{ margin: 0 }}>
          {said}
        </p>
      )}
    </section>
  );
}

export function People({ api }: { api: AdminApi }) {
  const [people, setPeople] = useState<PersonAccount[] | null>(null);
  const [ctx, setCtx] = useState<Context>({ custom: [], builtIn: {}, rows: null });
  const [problem, setProblem] = useState<string | null>(null);
  const [delivered, setDelivered] = useState<SignInDelivery | null>(null);
  const [removed, setRemoved] = useState<PersonAccount | null>(null);
  const [arrivals, setArrivals] = useState<OrganisationArrival[]>([]);
  const [arrivalsProblem, setArrivalsProblem] = useState<string | null>(null);
  const [joined, setJoined] = useState<string | null>(null);
  const [added, setAdded] = useState<PersonAccount | null>(null);
  // ADR-148 Amendment 8: Entra ID's words and form only when the Conduit says so; otherwise today's (an
  // invite refused on Entra is the Conduit's refusal, in its words).
  const [entra, setEntra] = useState(false);
  const [administratorSets, setAdministratorSets] = useState<AccessField[]>([]);
  const scheme = useScheme(api);
  // The roles and the case levels are the row's context; either failing leaves the rest working.
  const readContext = () => {
    listRoles(api)
      .then((c) =>
        setCtx((x) => ({
          ...x,
          custom: c.custom ?? [],
          builtIn: Object.fromEntries((c.built_in ?? []).map((b) => [b.id, b.rights as string[]])),
        })),
      )
      .catch(() => undefined);
    peopleRows(api)
      .then((rows) => setCtx((x) => ({ ...x, rows: rows && Array.isArray(rows.rows) ? rows : null })))
      .catch(() => undefined);
  };
  useEffect(() => {
    listPeople(api).then(setPeople).catch((e: Error) => setProblem(e.message));
    listArrivals(api).then(setArrivals).catch((e: Error) => setArrivalsProblem(e.message));
    signInKind(api)
      .then((k) => {
        setEntra(k?.kind === "entra");
        setAdministratorSets((k?.administrator_sets ?? []).filter((f): f is AccessField => EVERY_FIELD.includes(f as AccessField)));
      })
      .catch(() => setEntra(false));
    readContext();
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
      {entra && (
        <p className="label" style={{ margin: 0 }}>
          {entraPeopleWords(administratorSets)}
        </p>
      )}
      {added && (
        <p role="status" style={{ margin: 0 }}>
          {`${added.id} was added with no roles. Give them roles below; they hold them from their first sign-in.`}
        </p>
      )}
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
      {ctx.rows && <WithoutAuthor api={api} rows={ctx.rows} people={people} onNamed={readContext} />}
      <RoleAndLevelTips roles={ROLES} />
      <table className="table" aria-label="People and their roles">
        <thead>
          <tr>
            <th>Person</th>
            {ROLES.map((r) => (
              <th key={r.id} style={{ textAlign: "center" }}>{r.label}</th>
            ))}
            <th>
              Other grants<span className="visually-hidden">: custom roles, single rights and older roles</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {people.map((p) => (
            <PersonRow
              key={p.id}
              api={api}
              person={p}
              people={people}
              scheme={scheme}
              ctx={ctx}
              onSaved={saved}
              onDelivered={setDelivered}
              entra={entra}
              administratorSets={administratorSets}
              onRemoved={(gone) => {
                setRemoved(gone);
                setPeople((current) => (current ?? []).filter((x) => x.id !== gone.id));
              }}
            />
          ))}
        </tbody>
      </table>
      {entra ? (
        <>
          <AddByObjectIdForm
            api={api}
            onAdded={(person) => {
              setAdded(person);
              setPeople((current) => [...(current ?? []), person]);
            }}
          />
          <GuestsForm api={api} administratorSets={administratorSets} />
        </>
      ) : (
        <InviteForm
          api={api}
          scheme={scheme}
          onInvited={(delivery) => {
            setDelivered(delivery);
            setPeople((current) => [...(current ?? []), delivery.person]);
          }}
        />
      )}
    </>
  );
}
