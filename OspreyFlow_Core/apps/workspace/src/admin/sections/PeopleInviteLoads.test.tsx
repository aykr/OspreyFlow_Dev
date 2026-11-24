// @vitest-environment jsdom
// Slice AD5 (the faults AD2 was merged with, 19 Nov 2026): Admin › People › Invite a person reads everything it needs
// before it offers a choice, through one loader. The owner's design rule (19 Nov): the form is drawn only when everything
// it depends on has loaded; until then it says it is loading, or says in words what could not be read; never a choice,
// never a statement of what the inviter can give. What the form reads: the inviter (`GET /v1/me`), the handling scheme
// (`GET /v1/handling-scheme`), the roles catalogue (`GET /v1/admin/roles`, which decides which role boxes are offered),
// how people sign in (`GET /v1/admin/sign-in`, which decides whether this form is drawn at all, or Entra's instead; the one read exempt from "failed means no form": ADR-148 Amendment 8, as `PeopleEntra.test.tsx` holds, keeps Keycloak's People when it cannot be read, and the Conduit still refuses an invite on Entra), and
// the giver's rights (the `rights` prop, `GET /v1/me/rights` read by the App). Each is late and failed here, in every order.
//
// The fetch double refuses what the real routes refuse (rule 15; `invite_person_route`, `app.py`): `_within_your_reach`
// (an unknown classification or code is a 422; a clearance above the inviter's own, or a code they do not hold, a 403) and
// `_may_give` (an unknown role is a 422, a custom role that does not exist a 422; any of the nine administration rights the
// giver does not hold, conferred by a built-in role, a single `right:` grant or a custom role's current rights at the time of
// the post, is a 409 `beyond_your_rights`, with its words; the same list as `ADMINISTRATION_RIGHTS` in `People.tsx`, which
// `test_admin_giver_rights.py` holds to the schema). Older (legacy) role names are not modelled: the form never offers one. It refuses the reads the real routes refuse too: the
// roles catalogue, how people sign in, the people routes and the invite itself each carry `require_right(MANAGE_PEOPLE)`, so a
// giver the route's side does not hold that right for is answered 403 `right_required` on every one of them. And it sends the
// catalogue as the real route does (`list_roles_route`: every built-in role, each with its rights), and can send what the route
// never sends (an empty one, one lacking a role, one with a role's rights missing) to show the form refuses it. Synthetic names
// throughout (rule 9).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace } from "../AdminPlace";
import { InviterContext } from "../inviter";
import { ADMINISTRATION_RIGHTS, People } from "./People";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

const ORDER = ["PUBLIC", "OFFICIAL", "OFFICIAL-SENSITIVE"];
const SCHEME = { classification: ORDER, handling_codes: { P: {}, C: {} } };
const INVITER = { id: "adm-1", clearance: "OFFICIAL", org_unit: "unit-1", roles: ["people-admin"], receivable_handling_codes: ["P"] };
const ANA = { id: "u1", username: "ana", name: "Ana Analyst", enabled: true, roles: ["analyst"], clearance: "OFFICIAL", org_unit: "unit-1" };

/** What the giver holds on the route's side (`rights_for(principal.roles)`): the right to manage people, and no more. */
const HELD = new Set(["manage_people"]);
/** All nine administration rights (`schemas.rights.ADMINISTRATION_RIGHTS`): only a holder may give one (`giver_may_give`). */
const ADMINISTRATION = new Set<string>(ADMINISTRATION_RIGHTS);
/** The rights a role may hold, for `right:<name>` (the route's `allowed_role` accepts a single grant of any known right). */
const KNOWN_RIGHTS = new Set<string>([...ADMINISTRATION_RIGHTS, "investigate", "edit_pipelines", "author_rules", "read_reports"]);
/** The custom roles this deployment holds now, by id, with their current rights (`CustomRolesDep`; a test may change them). */
type CustomRoles = Record<string, string[]>;
/** The catalogue `GET /v1/admin/roles` answers (`_built_in_roles`: every built-in role the form offers, each with its rights;
 * the rights here are a short synthetic subset): Admin gives administration rights the giver does not hold. */
const CATALOGUE = {
  built_in: [
    { id: "analyst", label: "Analyst", rights: ["investigate"] },
    { id: "data_engineer", label: "Data Engineer", rights: ["edit_pipelines", "operate_schedules"] },
    { id: "osprey-admin", label: "Admin", rights: ["administer_system", "manage_people", "read_audit"] },
    { id: "reports_viewer", label: "Reports Viewer", rights: ["read_reports"] },
    { id: "rule_author", label: "Rule author", rights: ["author_rules"] },
    { id: "super_user", label: "Super user", rights: ["investigate", "author_rules"] },
  ],
  custom: [],
};
/** The roles the form offers a box for (`ROLES` in `People.tsx`), by id: the catalogue must name each, with its rights. */
const OFFERED = ["analyst", "data_engineer", "osprey-admin", "reports_viewer", "rule_author"];

// "403": the route's own refusal of a giver without the right (`require_right`: 403 `right_required`).
// "none", "partial" (lacking the role `omit`) and "unrighted" (the role `omit` named with no rights) are answers the real
// route never sends: a form drawn from one would offer a role its giver may not give, so each is refused.
type Mode = "ok" | "503" | "broken" | "bad" | "empty" | "403" | "none" | "partial" | "unrighted";
type Spec = { mode: Mode; gate?: Promise<void>; omit?: string };
type Reads = { me: Spec; scheme: Spec; roles: Spec; signin: Spec & { entra?: boolean } };
/** What the route's own side holds at the moment a request arrives (it can differ from what the Glass read a moment ago: a
 * role taken away, a scheme changed, a name taken since): a test changes it after the form is drawn. */
type Session = "valid" | "expired" | "keys_down" | "store_down" | "guest" | "not_admitted";
type Provider = "ok" | "refuses" | "down" | "mail_down";
type World = {
  held: Set<string>;
  custom: CustomRoles;
  inviter: { clearance: string; codes: string[] };
  scheme: { classification: string[]; handling_codes: Record<string, unknown> };
  taken: Set<string>;
  provider: Provider;
  audit: "ok" | "down";
  session: Session;
};
const KEYS = ["me", "scheme", "roles", "signin"] as const;
type Key = (typeof KEYS)[number];

const ok = (): Reads => ({ me: { mode: "ok" }, scheme: { mode: "ok" }, roles: { mode: "ok" }, signin: { mode: "ok" } });

/** `require_right(Right.MANAGE_PEOPLE)`, which every people, roles and sign-in route carries, checked before anything else. */
const needsManagePeople = (held: Set<string>): Response | null =>
  held.has("manage_people") ? null : json(403, { detail: { error: "right_required", right: "manage_people" } });

/** The invite route's refusals, in the route's own order and words. `held` is what the giver holds on the route's side. */
function refuse(body: { clearance: string; receivable_handling_codes: string[]; roles: string[] }, held: Set<string>, custom: CustomRoles): Response | null {
  const unheld = needsManagePeople(held);
  if (unheld) return unheld;
  if (!ORDER.includes(body.clearance)) return json(422, { detail: `${body.clearance} is not a classification of this deployment` });
  const unknown = body.receivable_handling_codes.filter((c) => !(c in SCHEME.handling_codes));
  if (unknown.length) return json(422, { detail: `not a handling code of this deployment: ${unknown.join(", ")}` });
  if (ORDER.indexOf(body.clearance) > ORDER.indexOf(INVITER.clearance))
    return json(403, { detail: { error: "above_your_clearance", clearance: body.clearance } });
  const beyond = body.receivable_handling_codes.filter((c) => !INVITER.receivable_handling_codes.includes(c)).sort();
  if (beyond.length) return json(403, { detail: { error: "handling_code_you_do_not_hold", codes: beyond } });
  // `allowed_role`: a built-in role, a single grant of a known right, or a custom role's name; else a 422.
  const names = CATALOGUE.built_in.map((r) => r.id);
  const known = (r: string) => names.includes(r) || (r.startsWith("right:") && KNOWN_RIGHTS.has(r.slice(6))) || r.startsWith("role:");
  const refused = body.roles.filter((r) => !known(r));
  if (refused.length) return json(422, { detail: `not a role or right this deployment grants: ${refused.join(", ")}` });
  const missing = body.roles.filter((r) => r.startsWith("role:") && !(r.slice(5) in custom));
  if (missing.length) return json(422, { detail: `no such custom role: ${missing.map((r) => r.slice(5)).join(", ")}` });
  // `rights_for(roles, current)`: each built-in role's rights, each single grant, each custom role's rights as they stand now.
  const rightsOf = (r: string): string[] =>
    r.startsWith("role:") ? (custom[r.slice(5)] ?? []) : r.startsWith("right:") ? [r.slice(6)] : (CATALOGUE.built_in.find((b) => b.id === r)?.rights ?? []);
  const given = new Set(body.roles.flatMap(rightsOf));
  const rights = [...given].filter((r) => ADMINISTRATION.has(r) && !held.has(r)).sort();
  if (rights.length)
    return json(409, { detail: { error: "beyond_your_rights", message: `you cannot give a right you do not hold: ${rights.join(", ")}`, rights } });
  return null;
}

/** Serves the four routes the form reads, each as `reads` says (answered at once, or held until its gate resolves and then
 * answering as its mode says), and the section's own. Returns what was posted and how often each path was read. */
function serve(reads: Reads, held: Set<string> = HELD, custom: CustomRoles = {}, over: Partial<World> = {}) {
  const world: World = {
    held,
    custom,
    inviter: { clearance: INVITER.clearance, codes: [...INVITER.receivable_handling_codes] },
    scheme: SCHEME,
    taken: new Set(),
    provider: "ok",
    audit: "ok",
    session: "valid",
    ...over,
  };
  const posted: unknown[] = [];
  const calls: Record<string, number> = {};
  const answer = async (spec: Spec, good: () => Response, bad: Response | (() => Response)): Promise<Response> => {
    await spec.gate;
    if (spec.mode === "ok") return good();
    if (spec.mode === "503") return json(503, {});
    if (spec.mode === "403") return needsManagePeople(new Set()) as Response;
    if (spec.mode === "broken") throw new TypeError("network down");
    return typeof bad === "function" ? bad() : bad;
  };
  // What the roles read answers in each mode the route itself never sends.
  const unreal = (): Response => {
    const { mode } = reads.roles;
    const omit = reads.roles.omit ?? "rule_author";
    if (mode === "none") return json(200, { built_in: [], custom: [] });
    if (mode === "partial") return json(200, { ...CATALOGUE, built_in: CATALOGUE.built_in.filter((r) => r.id !== omit) });
    if (mode === "unrighted")
      return json(200, { ...CATALOGUE, built_in: CATALOGUE.built_in.map((r) => (r.id === omit ? { id: r.id, label: r.label } : r)) });
    return json(200, { unexpected: true });
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      calls[path] = (calls[path] ?? 0) + 1;
      if (path === "/v1/me") return answer(reads.me, () => json(200, INVITER), json(200, { unexpected: true }));
      if (path === "/v1/handling-scheme")
        return answer(reads.scheme, () => json(200, SCHEME), json(200, reads.scheme.mode === "empty" ? { classification: [], handling_codes: {} } : {}));
      const admin = path.replace("/v1/admin/", "");
      // Every route below carries `require_right(MANAGE_PEOPLE)`: refused before anything else is read.
      const unheld = admin.startsWith("people") || ["roles", "sign-in", "organisation-arrivals"].includes(admin) ? needsManagePeople(held) : null;
      if (unheld) return unheld;
      if (admin === "roles") return answer(reads.roles, () => json(200, CATALOGUE), unreal);
      if (admin === "sign-in")
        return answer(reads.signin, () => json(200, { kind: reads.signin.entra ? "entra" : "keycloak" }), json(200, {}));
      if (admin === "people" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { clearance: string; receivable_handling_codes: string[]; roles: string[] };
        posted.push(body);
        return (
          refuse(body, held, custom) ??
          json(201, { person: { ...ANA, id: "u2", username: "new.person" }, delivery: "one_time_code", one_time_code: "ABCD-EFGH-JKLM-NPQR" })
        );
      }
      if (admin === "people") return json(200, [ANA]);
      if (admin === "people/rows") return json(200, { rows: [], without_author: [] });
      if (admin === "organisation-arrivals") return json(200, []);
      return json(200, {});
    }),
  );
  return { posted, calls, world };
}

const SAYS_WHAT_THEY_CAN_GIVE = /You hold|that clearance or lower|no handling code|the handling codes/;
const mustNotBeUsable = () => {
  expect(screen.queryByRole("form", { name: "Invite a person" })).toBeNull();
  expect(screen.queryByLabelText("Invite clearance")).toBeNull();
  expect(screen.queryByLabelText(/^Invite with handling code/)).toBeNull();
  expect(screen.queryByLabelText(/^Invite as /)).toBeNull();
  expect(screen.queryByRole("button", { name: "Invite" })).toBeNull();
  expect(screen.queryByLabelText("Sign-in name")).toBeNull();
  expect(screen.queryByLabelText("Invite unit")).toBeNull();
  expect(document.body.textContent).not.toMatch(SAYS_WHAT_THEY_CAN_GIVE);
};
const place = (rights: ReadonlySet<string> = new Set(["manage_people"])) =>
  render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={rights} />);
const sectionLoaded = () => waitFor(() => expect(screen.getByLabelText("Edit access for ana")).toBeTruthy());
const later = (ms = 25) => new Promise((resolve) => setTimeout(resolve, ms));
const hold = () => {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => (release = resolve));
  return { gate, release };
};

const WORDS: Record<Exclude<Key, "signin"> | "empty", string> = {
  me: "Your own clearance and handling codes could not be read, so nobody can be invited from here now.",
  scheme: "This deployment's classifications and handling codes could not be read, so nobody can be invited from here now.",
  empty: "This deployment's handling scheme has no classification levels, so nobody can be invited from here now.",
  roles: "The roles this deployment offers could not be read, so nobody can be invited from here now.",
};

/** The form as it must first be drawn, with every read in: the inviter's reach, and Admin withheld (the catalogue is in). */
const drawnCorrectly = (form: HTMLElement) => {
  expect(within(within(form).getByLabelText("Invite clearance")).queryAllByRole("option").map((o) => o.textContent)).toEqual([
    "PUBLIC",
    "OFFICIAL",
  ]);
  expect(form.textContent).toContain("You hold OFFICIAL, so you can give that clearance or lower, and the handling codes P.");
  const admin = within(form).getByLabelText("Invite as Admin");
  expect(admin.getAttribute("aria-disabled")).toBe("true");
  expect(document.getElementById(admin.getAttribute("aria-describedby") ?? "none")?.textContent).toContain("You cannot give Admin here");
  expect(within(form).getByLabelText("Invite as Analyst").getAttribute("aria-disabled")).toBeNull();
};

describe("the roles catalogue (GET /v1/admin/roles) decides which role boxes are offered, so the form waits for it", () => {
  it("when late: the form is not drawn until it arrives, then is drawn once, with the Admin box already withheld", async () => {
    const roles = hold();
    serve({ ...ok(), roles: { mode: "ok", gate: roles.gate } });
    place();
    expect((await screen.findByRole("status")).textContent).toContain("Reading what you can give");
    await sectionLoaded();
    await later();
    mustNotBeUsable();
    expect(screen.getByRole("status").textContent).toContain("Reading what you can give");
    roles.release();
    const form = await screen.findByRole("form", { name: "Invite a person" });
    drawnCorrectly(form); // at its first draw, never offered and then withheld
    await later();
    expect(screen.getByRole("form", { name: "Invite a person" })).toBe(form);
  });

  it.each([
    ["with a 503", "503"],
    ["with a network failure", "broken"],
    ["with an answer that is not a catalogue", "bad"],
  ] as const)("when it fails %s: says so in words, and offers no form, no role box and no statement", async (_how, mode) => {
    const { posted } = serve({ ...ok(), roles: { mode } });
    place();
    const words = await screen.findByRole("alert");
    expect(words.textContent).toContain(WORDS.roles);
    expect(words.textContent).toContain("Reload the page to try again.");
    await sectionLoaded();
    await later();
    mustNotBeUsable();
    expect(screen.queryByText(/Reading what you can give/)).toBeNull();
    expect(posted).toEqual([]);
  });

  it("when it fails after the form is drawn (a later read, as after naming an author), the drawn form stays", async () => {
    const live = ok();
    const { calls } = serve(live);
    const view = place();
    const form = await screen.findByRole("form", { name: "Invite a person" });
    live.roles.mode = "503";
    view.rerender(<AdminPlace apiBaseUrl="http://x" bearerToken="t2" rights={new Set(["manage_people"])} />);
    await waitFor(() => expect(calls["/v1/admin/roles"]).toBe(2));
    await later();
    expect(screen.getByRole("form", { name: "Invite a person" })).toBe(form);
    expect(screen.queryByText(/could not be read, so nobody can be invited/)).toBeNull();
  });
});

describe("the roles catalogue counts as read only when it names every role the form offers, each with its rights", () => {
  const BOXES = ["Analyst", "Data Engineer", "Admin", "Reports Viewer", "Rule author"];

  it("an empty built-in list is not a catalogue: the words, no form, and so no Admin box offered to a giver without its rights", async () => {
    const { posted } = serve({ ...ok(), roles: { mode: "none" } });
    place();
    const words = await screen.findByRole("alert");
    expect(words.textContent).toContain(WORDS.roles);
    await sectionLoaded();
    await later();
    mustNotBeUsable();
    expect(screen.queryByLabelText("Invite as Admin")).toBeNull();
    expect(posted).toEqual([]);
  });

  it.each(OFFERED)("a catalogue lacking %s is not read in full: the words, no form, and no box for any role", async (omit) => {
    serve({ ...ok(), roles: { mode: "partial", omit } });
    place();
    expect((await screen.findByRole("alert")).textContent).toContain(WORDS.roles);
    await sectionLoaded();
    await later();
    mustNotBeUsable();
    for (const box of BOXES) expect(screen.queryByLabelText(`Invite as ${box}`)).toBeNull();
  });

  it.each(OFFERED)("a catalogue naming %s with no rights is not read in full either", async (omit) => {
    serve({ ...ok(), roles: { mode: "unrighted", omit } });
    place();
    expect((await screen.findByRole("alert")).textContent).toContain(WORDS.roles);
    await sectionLoaded();
    await later();
    mustNotBeUsable();
  });

  it("a catalogue that names every role is drawn, with a box for each role the form offers and Admin withheld from this giver", async () => {
    serve(ok());
    place();
    const form = await screen.findByRole("form", { name: "Invite a person" });
    drawnCorrectly(form);
    for (const box of BOXES) expect(within(form).getByLabelText(`Invite as ${box}`)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("a catalogue with a role the form does not offer (Super user, as the real route sends) is still read in full: no box for it", async () => {
    serve(ok());
    place();
    const form = await screen.findByRole("form", { name: "Invite a person" });
    expect(within(form).queryByLabelText("Invite as Super user")).toBeNull();
  });
});

describe("a giver the route's side does not hold manage_people for is refused on every read, and the form offers nothing", () => {
  it("is told in words (the route's own refusal), with no form, no box and no statement, and nothing is posted", async () => {
    // The Glass believes the giver holds it (read at sign-in); the route's side holds none now (a role taken away since).
    const { posted, calls } = serve(ok(), new Set());
    place(new Set(["manage_people"]));
    const words = await screen.findByRole("alert");
    expect(words.textContent).toMatch(/Not done\./);
    await waitFor(() => {
      expect(calls["/v1/admin/roles"]).toBe(1);
      expect(calls["/v1/admin/sign-in"]).toBe(1);
      expect(calls["/v1/admin/people"]).toBe(1);
    });
    await later();
    mustNotBeUsable();
    expect(screen.queryByLabelText(/^Invite as /)).toBeNull();
    expect(posted).toEqual([]);
  });

  it("the double itself refuses each of those reads, and the invite, with 403 right_required", async () => {
    serve(ok(), new Set(["read_audit"]));
    for (const [path, init] of [["roles"], ["sign-in"], ["people"], ["people/rows"], ["organisation-arrivals"], ["people", { method: "POST", body: JSON.stringify({ clearance: "PUBLIC", receivable_handling_codes: [], roles: [] }) }]] as [string, RequestInit?][]) {
      const response = await fetch(`http://x/v1/admin/${path}`, init);
      expect([path, response.status, await response.json()]).toEqual([path, 403, { detail: { error: "right_required", right: "manage_people" } }]);
    }
  });
});

describe("a handling scheme with no classification levels is not loaded", () => {
  it("says in words that the scheme has no levels, and offers no form and no statement of what can be given", async () => {
    const { posted } = serve({ ...ok(), scheme: { mode: "empty" } });
    place();
    const words = await screen.findByRole("alert");
    expect(words.textContent).toContain(WORDS.empty);
    expect(words.textContent).not.toContain(WORDS.scheme); // its own words, not the unreadable scheme's
    await sectionLoaded();
    await later();
    mustNotBeUsable();
    expect(screen.queryByText(/Reading what you can give/)).toBeNull();
    expect(posted).toEqual([]);
  });

  it("is said even while another read is late, and a late empty scheme is the same", async () => {
    const roles = hold();
    const scheme = hold();
    serve({ ...ok(), roles: { mode: "ok", gate: roles.gate }, scheme: { mode: "empty", gate: scheme.gate } });
    place();
    await sectionLoaded();
    mustNotBeUsable();
    scheme.release();
    expect((await screen.findByRole("alert")).textContent).toContain(WORDS.empty);
    roles.release();
    await later();
    expect(screen.getByRole("alert").textContent).toContain(WORDS.empty);
    mustNotBeUsable();
  });
});

describe("how people sign in (GET /v1/admin/sign-in) decides whether this form is drawn at all, so the form waits for it", () => {
  it("when late: no form until it arrives (a form drawn for an Entra deployment would offer what it cannot do)", async () => {
    const signin = hold();
    serve({ ...ok(), signin: { mode: "ok", gate: signin.gate } });
    place();
    await sectionLoaded();
    await later();
    mustNotBeUsable();
    expect(screen.getByRole("status").textContent).toContain("Reading what you can give");
    signin.release();
    drawnCorrectly(await screen.findByRole("form", { name: "Invite a person" }));
  });

  it("when it says Entra ID, even late, no invite form is ever drawn: Add a person by object id is", async () => {
    const signin = hold();
    serve({ ...ok(), signin: { mode: "ok", gate: signin.gate, entra: true } });
    place();
    await sectionLoaded();
    mustNotBeUsable();
    signin.release();
    expect(await screen.findByRole("form", { name: "Add a person by object id" })).toBeTruthy();
    mustNotBeUsable();
  });

  it.each([
    ["with a 503", "503"],
    ["with a network failure", "broken"],
  ] as const)(
    "when it fails %s: it is Keycloak's People as before (`PeopleEntra.test.tsx`), but only once it has failed: late, no form until then",
    async (_how, mode) => {
      const signin = hold();
      serve({ ...ok(), signin: { mode, gate: signin.gate } });
      place();
      await sectionLoaded();
      await later();
      mustNotBeUsable();
      signin.release();
      drawnCorrectly(await screen.findByRole("form", { name: "Invite a person" }));
      expect(screen.queryByRole("alert")).toBeNull();
    },
  );
});

describe("the giver's own rights (the `rights` prop, read by the App) decide which role boxes are offered", () => {
  it("while they are not known the form is not drawn: every role would be offered", async () => {
    serve(ok());
    render(
      <InviterContext.Provider value={{ state: "ready", inviter: { clearance: "OFFICIAL", codes: ["P"] } }}>
        <People api={{ apiBaseUrl: "http://x", bearerToken: "t" }} />
      </InviterContext.Provider>,
    );
    await sectionLoaded();
    await later();
    mustNotBeUsable();
    expect(screen.getByRole("status").textContent).toContain("Reading what you can give");
  });
});

describe("each read, late and failed in turn", () => {
  const FAILURES: [Exclude<Key, "signin"> | "empty", Key, Mode][] = [
    ["me", "me", "503"],
    ["me", "me", "broken"],
    ["me", "me", "bad"],
    ["scheme", "scheme", "503"],
    ["scheme", "scheme", "broken"],
    ["scheme", "scheme", "bad"],
    ["empty", "scheme", "empty"],
    ["roles", "roles", "503"],
    ["roles", "roles", "broken"],
    ["roles", "roles", "bad"],
    ["roles", "roles", "403"],
    ["roles", "roles", "none"],
    ["roles", "roles", "partial"],
    ["roles", "roles", "unrighted"],
  ];

  it.each(FAILURES)("%s: %s read %s, at once, says its own words and no form", async (words, key, mode) => {
    serve({ ...ok(), [key]: { mode } });
    place();
    expect((await screen.findByRole("alert")).textContent).toContain(WORDS[words]);
    await sectionLoaded();
    await later();
    mustNotBeUsable();
  });

  it.each(FAILURES)("%s: %s read %s, late: reading until it fails, then its words; no form at any moment", async (words, key, mode) => {
    const late = hold();
    serve({ ...ok(), [key]: { mode, gate: late.gate } });
    place();
    await sectionLoaded();
    await later();
    mustNotBeUsable();
    expect(screen.getByRole("status").textContent).toContain("Reading what you can give");
    late.release();
    expect((await screen.findByRole("alert")).textContent).toContain(WORDS[words]);
    mustNotBeUsable();
  });

  it("two reads failing say both, each in its own words, and neither hides the other", async () => {
    serve({ ...ok(), me: { mode: "503" }, roles: { mode: "broken" }, scheme: { mode: "empty" } });
    place();
    const words = await screen.findByRole("alert");
    await waitFor(() => {
      const said = screen.getByRole("alert").textContent ?? "";
      expect(said).toContain(WORDS.me);
      expect(said).toContain(WORDS.empty);
      expect(said).toContain(WORDS.roles);
    });
    expect(words).toBeTruthy();
    mustNotBeUsable();
  });

  const permutations = (items: readonly Key[]): Key[][] =>
    items.length <= 1 ? [[...items]] : items.flatMap((x, i) => permutations([...items.slice(0, i), ...items.slice(i + 1)]).map((rest) => [x, ...rest]));

  it.each(permutations(KEYS).map((order) => [order.join(" → "), order] as const))(
    "no order of arrival draws the form early: %s",
    async (_name, order) => {
      const gates = Object.fromEntries(KEYS.map((k) => [k, hold()])) as Record<Key, ReturnType<typeof hold>>;
      serve({
        me: { mode: "ok", gate: gates.me.gate },
        scheme: { mode: "ok", gate: gates.scheme.gate },
        roles: { mode: "ok", gate: gates.roles.gate },
        signin: { mode: "ok", gate: gates.signin.gate },
      });
      place();
      await sectionLoaded();
      for (const key of order.slice(0, -1)) {
        mustNotBeUsable();
        gates[key].release();
        await later(8);
        mustNotBeUsable();
        expect(screen.queryByRole("status")?.textContent ?? "").toContain("Reading what you can give");
      }
      gates[order.at(-1) as Key].release();
      drawnCorrectly(await screen.findByRole("form", { name: "Invite a person" }));
    },
  );
});

/** The words a right has on screen and in the route's refusal (`right_name`, `rights_listed`), written out here, not computed. */
const RIGHT_WORDS: Record<string, string> = {
  administer_system: "Administer system",
  manage_people: "Manage people",
  manage_dashboards: "Manage dashboards",
  operate_schedules: "Operate schedules",
  manage_ontology: "Manage ontology",
  manage_geospatial: "Manage geospatial",
  read_audit: "Read audit",
  read_export_ledger: "Read export ledger",
  manage_models: "Manage models",
};

const AUTH = { Authorization: "Bearer t" };
const VALID = {
  username: "new.person",
  first_name: "",
  last_name: "",
  email: null as string | null,
  clearance: "PUBLIC",
  org_unit: "unit-1",
  receivable_handling_codes: [] as string[],
  roles: [] as string[],
};
/** One invite, posted straight at the double as the Glass sends it (a valid one, changed by `change`), against the route's side
 * as `over` makes it. */
async function ask(change: Record<string, unknown> = {}, over: Partial<World> = {}, headers: Record<string, string> = AUTH) {
  const { world, posted } = serve(ok(), over.held, over.custom, over);
  const response = await fetch("http://x/v1/admin/people", { method: "POST", headers, body: JSON.stringify({ ...VALID, ...change }) });
  return { status: response.status, body: (await response.json()) as unknown, world, posted };
}
const beyond = (rights: string[]) => ({
  status: 409,
  body: {
    detail: {
      error: "beyond_your_rights",
      message: `you cannot give a right you do not hold: ${
        rights.length === 1 ? RIGHT_WORDS[rights[0] as string] : `${rights.slice(0, -1).map((r) => RIGHT_WORDS[r]).join(", ")} and ${RIGHT_WORDS[rights.at(-1) as string]}`
      }`,
      rights,
    },
  },
});

describe("the double refuses an invite the real giver rule refuses (`_may_give`, `giver_may_give`), for any of the nine administration rights", () => {
  const post = (roles: string[], held: Set<string> = HELD, custom: CustomRoles = {}) => ask({ roles }, { held, custom });

  it("takes all nine administration rights, the list the form itself holds", () => {
    expect(ADMINISTRATION.size).toBe(9);
    expect(ADMINISTRATION.has("operate_schedules")).toBe(true);
  });

  it("refuses Data Engineer from a giver holding manage_people alone: operate_schedules is an administration right", async () => {
    expect(pick(await post(["data_engineer"]))).toEqual(beyond(["operate_schedules"]));
  });

  it("accepts Data Engineer from a giver who holds operate_schedules, and Analyst from any giver (the double is not refusing everything)", async () => {
    expect((await post(["data_engineer"], new Set(["manage_people", "operate_schedules"]))).status).toBe(201);
    expect((await post(["analyst"])).status).toBe(201);
  });

  // The six the old double did not know: each, given singly (`right:<name>`), is refused only because of that one right.
  it.each(ADMINISTRATION_RIGHTS.filter((r) => !["administer_system", "manage_people", "read_audit"].includes(r)))(
    "refuses the single right %s, and only it, from a giver who does not hold it; accepts it from one who does",
    async (right) => {
      expect(pick(await post([`right:${right}`]))).toEqual(beyond([right]));
      expect((await post([`right:${right}`], new Set(["manage_people", right]))).status).toBe(201);
    },
  );

  it("reads a custom role's rights as they stand when it is posted: refused for an administration right it holds now, accepted after it is changed", async () => {
    const custom: CustomRoles = { reviewers: ["investigate", "read_export_ledger"] };
    expect(pick(await post(["role:reviewers"], HELD, custom))).toEqual(beyond(["read_export_ledger"]));
    custom.reviewers = ["investigate"]; // changed since: it no longer holds one
    expect((await post(["role:reviewers"], HELD, custom)).status).toBe(201);
    custom.reviewers = ["investigate", "manage_models"]; // and changed again
    expect(pick(await post(["role:reviewers"], HELD, custom))).toEqual(beyond(["manage_models"]));
  });

  it("names every right it refuses as the screens do, sorted, through `rights_listed`: 'A, B and C', never the raw ids", async () => {
    expect(pick(await post(["osprey-admin", "data_engineer"]))).toEqual(beyond(["administer_system", "operate_schedules", "read_audit"]));
    const two = (await post(["osprey-admin"], new Set(["manage_people", "read_audit"]))).body as { detail: { message: string } };
    expect(two.detail.message).toBe("you cannot give a right you do not hold: Administer system");
    const both = (await post(["osprey-admin"])).body as { detail: { message: string } };
    expect(both.detail.message).toBe("you cannot give a right you do not hold: Administer system and Read audit");
    expect(both.detail.message).not.toMatch(/administer_system|read_audit/);
  });
});

/** The status and body of an answer, without the world it was asked of. */
const pick = ({ status, body }: { status: number; body: unknown }) => ({ status, body });
const err = (type: string, loc: string, msg: string, input: unknown, ctx?: Record<string, unknown>) => ({
  type,
  loc: ["body", loc],
  msg,
  input,
  ...(ctx ? { ctx } : {}),
});
const USERNAME_RULE = "^[a-z0-9][a-z0-9._-]{1,62}$";
const EMAIL_RULE = "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$";

// Every answer `POST /v1/admin/people` can give (read from `invite_person_route`, `_within_your_reach`, `_may_give`,
// `allowed_role`, `giver_may_give`, `identity_admin.invite`, `get_principal`, `require_right` and the app's exception
// handlers, 24 Nov 2026), in the order the route reaches them, each with its status, its error code and its words. The form
// posts only ids from `ROLES`, a username and email the person typed, and the clearance and codes it offered, so a refusal the
// form cannot reach by itself (an unknown role, a missing custom role, a role of an older name, a single right, too many roles
// or codes, a missing token, a dashboard's identity) is held by the double all the same and is shown here by a post straight
// at it.
describe("the double answers each refusal of the invite route with the route's status, error code and words", () => {
  const detail = (status: number, body: unknown) => ({ status, body });

  it("1. no credentials: 401 'Not authenticated' (the bearer scheme), before the route's own rules", async () => {
    expect(pick(await ask({}, {}, {}))).toEqual(detail(401, { detail: "Not authenticated" }));
  });

  it.each([
    ["2. a token the resolver rejects: 401, its words", "expired", 401, { detail: "token rejected: Signature has expired" }],
    [
      "3. the identity provider's keys unreachable: 503 in words, never 'token rejected'",
      "keys_down",
      503,
      { detail: { error: "identity_provider_unavailable", message: "sign-in is unavailable: the identity provider could not be reached. Try again shortly." } },
    ],
    [
      "4. the person's stored roles unreadable: 503 in words",
      "store_down",
      503,
      { detail: { error: "people_store_unavailable", message: "sign-in is unavailable: this deployment could not read your roles. Try again shortly." } },
    ],
    ["5. a refusal of the sign-in with its tag (a guest account not admitted): 401, words and error", "guest", 401, { detail: "guest sign-in is not admitted here", error: "guest_not_admitted" }],
    [
      "6. an identity admitted to named routes alone (a dashboard's), asking another: 403 route_not_admitted",
      "not_admitted",
      403,
      { detail: { error: "route_not_admitted", message: "this identity is admitted only to GET /v1/handling-scheme, GET /v1/me" } },
    ],
  ] as const)("%s", async (_name, session, status, body) => {
    expect(pick(await ask({}, { session }))).toEqual(detail(status, body));
  });

  it("6b. an identity admitted to named routes alone is still answered on a route it is admitted to", async () => {
    serve(ok(), HELD, {}, { session: "not_admitted" });
    expect((await fetch("http://x/v1/me", { headers: AUTH })).status).toBe(200);
  });

  it("7. a giver without manage_people: 403 right_required, naming the right, before the body is read (an invalid body is not 422 for them)", async () => {
    const refused = detail(403, { detail: { error: "right_required", right: "manage_people" } });
    expect(pick(await ask({}, { held: new Set() }))).toEqual(refused);
    expect(pick(await ask({ username: "Bad Name" }, { held: new Set() }))).toEqual(refused);
  });

  it("8. a body the schema refuses: 422, FastAPI's list, one entry for each field wrong, in the schema's order, with its words", async () => {
    const codes = Array.from({ length: 17 }, () => "a");
    const roles = Array.from({ length: 65 }, () => "analyst");
    expect(
      pick(
        await ask({
          clearance: "",
          org_unit: "u".repeat(61),
          receivable_handling_codes: codes,
          username: "Bad Name",
          first_name: "f".repeat(61),
          last_name: "l".repeat(61),
          email: "nope",
          roles,
        }),
      ),
    ).toEqual(
      detail(422, {
        detail: [
          err("string_too_short", "clearance", "String should have at least 1 character", "", { min_length: 1 }),
          err("string_too_long", "org_unit", "String should have at most 60 characters", "u".repeat(61), { max_length: 60 }),
          err("value_error", "receivable_handling_codes", "Value error, at most 16 handling codes", codes, { error: {} }),
          err("string_pattern_mismatch", "username", `String should match pattern '${USERNAME_RULE}'`, "Bad Name", { pattern: USERNAME_RULE }),
          err("string_too_long", "first_name", "String should have at most 60 characters", "f".repeat(61), { max_length: 60 }),
          err("string_too_long", "last_name", "String should have at most 60 characters", "l".repeat(61), { max_length: 60 }),
          err("string_pattern_mismatch", "email", `String should match pattern '${EMAIL_RULE}'`, "nope", { pattern: EMAIL_RULE }),
          err("too_long", "roles", "List should have at most 64 items after validation, not 65", roles, { field_type: "List", max_length: 64, actual_length: 65 }),
        ],
      }),
    );
    expect((await ask({ username: "a" })).status).toBe(422); // two characters at least
    expect((await ask({ username: "ab" })).status).toBe(201);
    expect((await ask({ username: "-ab" })).status).toBe(422);
  });

  it("9. a clearance this deployment does not have: 422 not_allowed, in words", async () => {
    expect(pick(await ask({ clearance: "SECRET" }))).toEqual(detail(422, { error: "not_allowed", detail: "SECRET is not a classification of this deployment" }));
  });

  it("10. handling codes this deployment does not have: 422 not_allowed, naming them in the order sent", async () => {
    expect(pick(await ask({ receivable_handling_codes: ["Z", "P", "Y"] }))).toEqual(
      detail(422, { error: "not_allowed", detail: "not a handling code of this deployment: Z, Y" }),
    );
  });

  it("11. a clearance above the giver's own: 403 above_your_clearance, naming what was asked", async () => {
    expect(pick(await ask({ clearance: "OFFICIAL-SENSITIVE" }))).toEqual(detail(403, { detail: { error: "above_your_clearance", clearance: "OFFICIAL-SENSITIVE" } }));
    // a giver whose own clearance is not on this deployment's scale holds no clearance to give from
    expect((await ask({}, { inviter: { clearance: "SECRET", codes: [] } })).status).toBe(403);
  });

  it("12. handling codes the giver does not hold: 403 handling_code_you_do_not_hold, sorted", async () => {
    expect(pick(await ask({ receivable_handling_codes: ["P", "C"] }))).toEqual(detail(403, { detail: { error: "handling_code_you_do_not_hold", codes: ["C"] } }));
    expect(pick(await ask({ receivable_handling_codes: ["P", "C"] }, { inviter: { clearance: "OFFICIAL", codes: [] } }))).toEqual(
      detail(403, { detail: { error: "handling_code_you_do_not_hold", codes: ["C", "P"] } }),
    );
  });

  it("13. a role or right this deployment does not grant: 422 not_allowed, naming each in the order sent (super_user is in the catalogue and is none of these)", async () => {
    const words = (names: string) => detail(422, { error: "not_allowed", detail: `not a role or right this deployment grants: ${names}` });
    expect(pick(await ask({ roles: ["super_user"] }))).toEqual(words("super_user"));
    expect(pick(await ask({ roles: ["analyst", "nobody", "super_user"] }))).toEqual(words("nobody, super_user"));
    expect(pick(await ask({ roles: ["right:made_up"] }))).toEqual(words("right:made_up"));
    expect(pick(await ask({ roles: ["right:"] }))).toEqual(words("right:"));
    expect(pick(await ask({ roles: ["role:"] }))).toEqual(words("role:"));
    expect(pick(await ask({ roles: ["role:Upper"] }))).toEqual(words("role:Upper")); // a custom role's id is lower-case letters and digits
    expect(pick(await ask({ roles: [`role:${"a".repeat(33)}`] }))).toEqual(words(`role:${"a".repeat(33)}`));
    expect(pick(await ask({ roles: ["role:made_up"] }))).toEqual(words("role:made_up")); // an underscore is not in a custom role's id
  });

  it("14. a custom role that does not exist (now): 422, the plain words, no error code; each missing one named", async () => {
    expect(pick(await ask({ roles: ["role:gone", "role:reviewers", "role:also"] }, { custom: { reviewers: [] } }))).toEqual(
      detail(422, { detail: "no such custom role: gone, also" }),
    );
  });

  it("15. a right the giver does not hold: 409 beyond_your_rights, words as the screens say the rights, and the ids", async () => {
    expect(pick(await ask({ roles: ["osprey-admin"] }))).toEqual(beyond(["administer_system", "read_audit"]));
  });

  it("15b. an older role's rights count: Compliance confers read_export_ledger, an administration right, so it is refused too (the form never offers it)", async () => {
    expect(pick(await ask({ roles: ["compliance"] }))).toEqual(beyond(["read_export_ledger"]));
    expect((await ask({ roles: ["source_author", "source_approver", "loader"] })).status).toBe(201); // none confers an administration right
    expect((await ask({ roles: ["compliance"] }, { held: new Set(["manage_people", "read_export_ledger"]) })).status).toBe(201);
  });

  it("16. a sign-in name or email address already held: 409 person_exists, in words; and an invitation made holds it afterwards", async () => {
    const held = detail(409, { error: "person_exists", detail: "that sign-in name or email address is already held" });
    expect(pick(await ask({ username: "ana" }, { taken: new Set(["ana"]) }))).toEqual(held);
    expect(pick(await ask({ email: "a@example.test" }, { taken: new Set(["a@example.test"]) }))).toEqual(held);
    const first = await ask({ username: "new.one" });
    expect(first.status).toBe(201);
    expect(first.world.taken.has("new.one")).toBe(true);
    const response = await fetch("http://x/v1/admin/people", { method: "POST", headers: AUTH, body: JSON.stringify({ ...VALID, username: "new.one" }) });
    expect([response.status, await response.json()]).toEqual([409, held.body]);
  });

  it("17. the identity provider refuses the person: 422 not_allowed, its own words after ours", async () => {
    expect(pick(await ask({}, { provider: "refuses" }))).toEqual(
      detail(422, { error: "not_allowed", detail: 'the identity provider refused the person: {"errorMessage":"Password policy not met"}' }),
    );
  });

  it("18. the identity provider does not create the person: 502 identity_provider_refused, with the status it gave", async () => {
    expect(pick(await ask({}, { provider: "down" }))).toEqual(
      detail(502, { error: "identity_provider_refused", detail: "the identity provider did not create the person (500)" }),
    );
  });

  it("19. the sign-in email cannot be sent (an email address given, mail failing): 502, and no half-made account is kept", async () => {
    const answer = await ask({ email: "a@example.test" }, { provider: "mail_down" });
    expect(pick(answer)).toEqual(detail(502, { error: "identity_provider_refused", detail: "the sign-in email could not be sent: Failed to send email" }));
    expect(answer.world.taken.size).toBe(0);
    expect((await ask({}, { provider: "mail_down" })).status).toBe(201); // no address: the one-time code is the way in, no mail to fail
  });

  it("20. the audit record cannot be written after the account is made: 503 audit_unavailable (the one case the platform fails closed); the account exists", async () => {
    const answer = await ask({}, { audit: "down" });
    expect(pick(answer)).toEqual(detail(503, { error: "audit_unavailable", detail: "the audit stream could not be written" }));
    expect(answer.world.taken.has("new.person")).toBe(true);
  });

  it("21. a made person: 201, the person and how they sign in; the one-time code only when there is no emailed link", async () => {
    const answer = await ask({ roles: ["analyst"] });
    expect(answer.status).toBe(201);
    expect(answer.body).toMatchObject({ person: { username: "new.person" }, delivery: "one_time_code", one_time_code: "ABCD-EFGH-JKLM-NPQR" });
  });
});

type Fill = { username?: string; unit?: string; email?: string; level?: string; codes?: string[]; role?: string };
/** Draws the form (the reads all succeed), lets the route's side change, fills the form as `fill` says and invites. */
async function inviteAfter(change: (w: World) => void, fill: Fill = {}, rights: ReadonlySet<string> = new Set(["manage_people"])) {
  const { world, posted } = serve(ok(), new Set(HELD));
  place(rights);
  const form = await screen.findByRole("form", { name: "Invite a person" });
  change(world);
  fireEvent.change(within(form).getByLabelText("Sign-in name"), { target: { value: fill.username ?? "new.person" } });
  fireEvent.change(within(form).getByLabelText("Invite unit"), { target: { value: fill.unit ?? "unit-1" } });
  if (fill.email) fireEvent.change(within(form).getByLabelText("Email (optional)"), { target: { value: fill.email } });
  if (fill.level) fireEvent.change(within(form).getByLabelText("Invite clearance"), { target: { value: fill.level } });
  for (const code of fill.codes ?? []) fireEvent.click(within(form).getByLabelText(`Invite with handling code ${code}`));
  fireEvent.click(within(form).getByLabelText(`Invite as ${fill.role ?? "Analyst"}`));
  fireEvent.click(within(form).getByRole("button", { name: "Invite" }));
  const words = (await within(form).findByRole("alert")).textContent ?? "";
  return { words, posted, world, form };
}

describe("every refusal the form can reach is shown in the route's own words, and the form offers no more than before", () => {
  it.each([
    ["a role taken away since: 403 right_required", (w: World) => w.held.clear(), {}, /Not done\./],
    ["a name taken since: 409 person_exists", (w: World) => w.taken.add("taken.one"), { username: "taken.one" }, /That sign-in name or email address is already held\./],
    ["the identity provider refuses the person", (w: World) => (w.provider = "refuses"), {}, /the identity provider refused the person: \{"errorMessage":"Password policy not met"\}/],
    ["the identity provider does not create the person", (w: World) => (w.provider = "down"), {}, /the identity provider did not create the person \(500\)/],
    ["the sign-in email cannot be sent", (w: World) => (w.provider = "mail_down"), { email: "a@example.test" }, /the sign-in email could not be sent: Failed to send email/],
    ["the audit record cannot be written", (w: World) => (w.audit = "down"), {}, /The Admin area could not complete that \(503\)\./],
    ["the token expired since", (w: World) => (w.session = "expired"), {}, /The Admin area could not complete that \(401\)\./],
    ["the identity provider's keys cannot be read", (w: World) => (w.session = "keys_down"), {}, /sign-in is unavailable: the identity provider could not be reached\. Try again shortly\./],
    ["the person's stored roles cannot be read", (w: World) => (w.session = "store_down"), {}, /sign-in is unavailable: this deployment could not read your roles\. Try again shortly\./],
    ["a sign-in name the schema refuses", () => {}, { username: "Bad Name" }, /The Admin area could not complete that \(422\)\./],
    ["an email address the schema refuses (the box takes \"a@b\", the schema wants a dot after the @)", () => {}, { email: "a@b" }, /The Admin area could not complete that \(422\)\./],
    ["a unit longer than the schema allows", () => {}, { unit: "u".repeat(61) }, /The Admin area could not complete that \(422\)\./],
    ["a clearance above the giver's own now (theirs lowered since)", (w: World) => (w.inviter.clearance = "PUBLIC"), { level: "OFFICIAL" }, /You cannot give a clearance above your own \(OFFICIAL asked\)\./],
    ["a handling code the giver no longer holds", (w: World) => (w.inviter.codes = []), { codes: ["P"] }, /You cannot give a handling code you do not hold yourself \(P\)\./],
    ["a classification the scheme no longer has", (w: World) => (w.scheme = { classification: ["PUBLIC"], handling_codes: SCHEME.handling_codes }), { level: "OFFICIAL" }, /OFFICIAL is not a classification of this deployment/],
    ["a handling code the scheme no longer has", (w: World) => (w.scheme = { classification: ORDER, handling_codes: { C: {} } }), { codes: ["P"] }, /not a handling code of this deployment: P/],
  ] as [string, (w: World) => void, Fill, RegExp][])("%s", async (_name, change, fill, expected) => {
    const { words, posted } = await inviteAfter(change, fill);
    expect(words).toMatch(expected);
    // The route reads the body only for a giver who holds the right (`require_right` is first): nothing reaches it otherwise.
    expect(posted).toHaveLength(/Not done\./.test(words) ? 0 : 1);
  });

  it("offers Data Engineer to a giver the Glass believes holds operate_schedules, and the route refuses it in the screens' words; withholds it from one who does not", async () => {
    const { words, posted } = await inviteAfter(() => {}, { role: "Data Engineer" }, new Set(["manage_people", "operate_schedules"]));
    expect(words).toContain("you cannot give a right you do not hold: Operate schedules");
    expect(words).not.toContain("operate_schedules");
    expect(posted).toHaveLength(1);
    cleanup();
    serve(ok(), HELD);
    place();
    const plain = await screen.findByRole("form", { name: "Invite a person" });
    expect(within(plain).getByLabelText("Invite as Data Engineer").getAttribute("aria-disabled")).toBe("true");
  });

  it("offers Admin to a giver the Glass believes holds its rights, and the route refuses it in the screens' words by the Invite button", async () => {
    const { words, posted } = await inviteAfter(() => {}, { role: "Admin" }, new Set(["manage_people", "administer_system", "read_audit"]));
    expect(posted[0]).toMatchObject({ roles: ["osprey-admin"], clearance: "PUBLIC" });
    expect(words).toContain("you cannot give a right you do not hold: Administer system and Read audit");
    expect(words).not.toMatch(/administer_system|read_audit/);
  });

  it("withholds Admin from a giver who does not hold it, so the route is never asked for it; Analyst is accepted", async () => {
    const { posted } = serve(ok());
    place();
    const form = await screen.findByRole("form", { name: "Invite a person" });
    fireEvent.change(within(form).getByLabelText("Sign-in name"), { target: { value: "new.person" } });
    fireEvent.change(within(form).getByLabelText("Invite unit"), { target: { value: "unit-1" } });
    fireEvent.click(within(form).getByLabelText("Invite as Admin")); // withheld: does nothing
    fireEvent.click(within(form).getByLabelText("Invite as Analyst"));
    fireEvent.click(within(form).getByRole("button", { name: "Invite" }));
    expect(await screen.findByText("ABCD-EFGH-JKLM-NPQR")).toBeTruthy();
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({ roles: ["analyst"] });
  });
});
