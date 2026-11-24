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
function serve(reads: Reads, held: Set<string> = HELD, custom: CustomRoles = {}) {
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
  return { posted, calls };
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

describe("the double refuses an invite the real giver rule refuses (`_may_give`, `giver_may_give`), for any of the nine administration rights", () => {
  const post = async (roles: string[], held: Set<string> = HELD, custom: CustomRoles = {}) => {
    serve(ok(), held, custom);
    const response = await fetch("http://x/v1/admin/people", {
      method: "POST",
      body: JSON.stringify({ clearance: "PUBLIC", receivable_handling_codes: [], roles }),
    });
    return { status: response.status, body: (await response.json()) as { detail: { error?: string; rights?: string[]; message?: string } | string } };
  };
  const beyond = (rights: string[]) => ({
    status: 409,
    body: { detail: { error: "beyond_your_rights", message: `you cannot give a right you do not hold: ${rights.join(", ")}`, rights } },
  });

  it("takes all nine administration rights, the list the form itself holds", () => {
    expect(ADMINISTRATION.size).toBe(9);
    expect(ADMINISTRATION.has("operate_schedules")).toBe(true);
  });

  it("refuses Data Engineer from a giver holding manage_people alone: operate_schedules is an administration right", async () => {
    expect(await post(["data_engineer"])).toEqual(beyond(["operate_schedules"]));
  });

  it("accepts Data Engineer from a giver who holds operate_schedules, and Analyst from any giver (the double is not refusing everything)", async () => {
    expect((await post(["data_engineer"], new Set(["manage_people", "operate_schedules"]))).status).toBe(201);
    expect((await post(["analyst"])).status).toBe(201);
  });

  // The six the old double did not know: each, given singly (`right:<name>`), is refused only because of that one right.
  it.each(ADMINISTRATION_RIGHTS.filter((r) => !["administer_system", "manage_people", "read_audit"].includes(r)))(
    "refuses the single right %s, and only it, from a giver who does not hold it; accepts it from one who does",
    async (right) => {
      expect(await post([`right:${right}`])).toEqual(beyond([right]));
      expect((await post([`right:${right}`], new Set(["manage_people", right]))).status).toBe(201);
    },
  );

  it("reads a custom role's rights as they stand when it is posted: refused for an administration right it holds now, accepted after it is changed", async () => {
    const custom: CustomRoles = { reviewers: ["investigate", "read_export_ledger"] };
    expect(await post(["role:reviewers"], HELD, custom)).toEqual(beyond(["read_export_ledger"]));
    custom.reviewers = ["investigate"]; // changed since: it no longer holds one
    expect((await post(["role:reviewers"], HELD, custom)).status).toBe(201);
    custom.reviewers = ["investigate", "manage_models"]; // and changed again
    expect(await post(["role:reviewers"], HELD, custom)).toEqual(beyond(["manage_models"]));
  });

  it("refuses a custom role that does not exist (422), a name no role has (422), and names every right it refuses, sorted", async () => {
    expect((await post(["role:gone"])).body).toEqual({ detail: "no such custom role: gone" });
    expect((await post(["nobody"])).body).toEqual({ detail: "not a role or right this deployment grants: nobody" });
    expect(await post(["osprey-admin", "data_engineer"])).toEqual(beyond(["administer_system", "operate_schedules", "read_audit"]));
  });

  it("offers Data Engineer to a giver the Glass believes holds operate_schedules, and the route refuses it in words; withholds it from one who does not", async () => {
    const { posted } = serve(ok(), HELD);
    place(new Set(["manage_people", "operate_schedules"]));
    const form = await screen.findByRole("form", { name: "Invite a person" });
    expect(within(form).getByLabelText("Invite as Data Engineer").getAttribute("aria-disabled")).toBeNull();
    fireEvent.change(within(form).getByLabelText("Sign-in name"), { target: { value: "new.person" } });
    fireEvent.change(within(form).getByLabelText("Invite unit"), { target: { value: "unit-1" } });
    fireEvent.click(within(form).getByLabelText("Invite as Data Engineer"));
    fireEvent.click(within(form).getByRole("button", { name: "Invite" }));
    expect((await within(form).findByRole("alert")).textContent).toContain("you cannot give a right you do not hold: operate_schedules");
    expect(posted).toHaveLength(1);
    cleanup();
    serve(ok(), HELD);
    place();
    const plain = await screen.findByRole("form", { name: "Invite a person" });
    expect(within(plain).getByLabelText("Invite as Data Engineer").getAttribute("aria-disabled")).toBe("true");
  });
});

describe("what the route refuses, which the form does not hide (the double refuses as the route does)", () => {
  it("offers Admin to a giver the Glass believes holds its rights, and the route refuses it in words by the Invite button", async () => {
    // The giver's rights were read at sign-in; the route's side holds fewer now (a role taken away since).
    const { posted } = serve(ok(), HELD);
    place(new Set(["manage_people", "administer_system", "read_audit"]));
    const form = await screen.findByRole("form", { name: "Invite a person" });
    expect(within(form).getByLabelText("Invite as Admin").getAttribute("aria-disabled")).toBeNull();
    fireEvent.change(within(form).getByLabelText("Sign-in name"), { target: { value: "new.person" } });
    fireEvent.change(within(form).getByLabelText("Invite unit"), { target: { value: "unit-1" } });
    fireEvent.click(within(form).getByLabelText("Invite as Admin"));
    fireEvent.click(within(form).getByRole("button", { name: "Invite" }));
    const summary = await within(form).findByRole("alert");
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({ roles: ["osprey-admin"], clearance: "PUBLIC" });
    expect(summary.textContent).toContain("you cannot give a right you do not hold: administer_system, read_audit");
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
