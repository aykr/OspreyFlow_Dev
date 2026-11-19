// @vitest-environment jsdom
// Slice AD2 (found 17 Nov on the GOV.UK demo): Admin › People › Invite a person offers only what the inviter can give,
// and a refusal is said by the Invite button as an error summary, in words, with focus on it (`02_GLASS_FRONTEND.md`:
// a refusal is said on the form; GOV.UK forms use an error summary). The Conduit stays the authority
// (`_within_your_reach`, `app.py`): the Glass's filter is a convenience, so the fetch double below refuses the way the
// real route does and the summary is proved from a refusal it cannot avoid by filtering (`GET /v1/me` says the inviter
// holds more than the route will let them give, as after a clearance lowered since sign-in). The form is drawn only once
// the inviter's own details have arrived, so no choice is made before them. Synthetic names throughout (rule 9).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace } from "../AdminPlace";
import { givableCodes, givableLevels } from "../inviter";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

const ORDER = ["PUBLIC", "OFFICIAL", "OFFICIAL-SENSITIVE"];
const SCHEME = { classification: ORDER, handling_codes: { P: {}, C: {}, R: {} } };
/** The inviter: OFFICIAL, and able to receive P alone. */
const INVITER = { id: "adm-1", clearance: "OFFICIAL", org_unit: "unit-1", roles: ["osprey-admin"], receivable_handling_codes: ["P"] };
const ANA = { id: "u1", username: "ana", name: "Ana Analyst", enabled: true, roles: ["analyst"], clearance: "OFFICIAL", org_unit: "unit-1" };

/** The Conduit's `_within_your_reach`, as the real route answers it: unknown values first, then the clearance, then the
 * handling codes, each a 403 with the detail the Glass reads. */
function reach(body: { clearance: string; receivable_handling_codes: string[] }): Response | null {
  if (!ORDER.includes(body.clearance)) return json(422, { detail: `${body.clearance} is not a classification of this deployment` });
  if (ORDER.indexOf(body.clearance) > ORDER.indexOf(INVITER.clearance))
    return json(403, { detail: { error: "above_your_clearance", clearance: body.clearance } });
  const beyond = body.receivable_handling_codes.filter((c) => !INVITER.receivable_handling_codes.includes(c)).sort();
  if (beyond.length) return json(403, { detail: { error: "handling_code_you_do_not_hold", codes: beyond } });
  return null;
}

/** What `GET /v1/me` answers: the inviter's real details (`own`); more than the route will let them give (`stale`, as after
 * a clearance lowered since sign-in, so the Glass offers what the route refuses); a clearance outside the scheme
 * (`outside`); or no answer (`down`). `meGate`: when given, `GET /v1/me` answers only once it resolves. */
type Me = "own" | "stale" | "outside" | "down";
const STALE = { ...INVITER, clearance: "OFFICIAL-SENSITIVE", receivable_handling_codes: ["P", "C", "R"] };
const OUTSIDE = { ...INVITER, clearance: "TOP-SECRET", receivable_handling_codes: [] };

function serve(me: Me, meGate?: Promise<void>) {
  const posted: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      if (path === "/v1/me") {
        await meGate;
        return me === "down" ? json(503, {}) : json(200, { own: INVITER, stale: STALE, outside: OUTSIDE }[me]);
      }
      if (path === "/v1/handling-scheme") return json(200, SCHEME);
      const admin = path.replace("/v1/admin/", "");
      if (admin === "people" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { clearance: string; receivable_handling_codes: string[] };
        posted.push(body);
        return (
          reach(body) ??
          json(201, { person: { ...ANA, id: "u2", username: "new.person" }, delivery: "one_time_code", one_time_code: "ABCD-EFGH-JKLM-NPQR" })
        );
      }
      if (admin === "people") return json(200, [ANA]);
      if (admin === "people/rows") return json(200, { rows: [], without_author: [] });
      if (admin === "roles") return json(200, { built_in: [], custom: [] });
      if (admin === "organisation-arrivals") return json(200, []);
      if (admin === "sign-in") return json(200, { kind: "keycloak" });
      return json(200, {});
    }),
  );
  return posted;
}

const optionNames = (form: HTMLElement) =>
  within(within(form).getByLabelText("Invite clearance")).queryAllByRole("option").map((o) => o.textContent);

/** The form, once drawn (the inviter's details are in) and its choices are read; `offered` is what the select then holds. */
const open = async (offered: string[] = ["PUBLIC", "OFFICIAL"]) => {
  render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(["manage_people"])} />);
  const form = await screen.findByRole("form", { name: "Invite a person" });
  await waitFor(() => expect(optionNames(form)).toEqual(offered));
  return form;
};

describe("Invite a person offers only what the inviter can give", () => {
  it("offers no clearance above the inviter's own, and no handling code outside their receivable set", async () => {
    serve("own");
    const form = await open();
    expect(within(form).queryByRole("option", { name: "OFFICIAL-SENSITIVE" })).toBeNull();
    expect(within(form).getByLabelText("Invite with handling code P")).toBeTruthy();
    expect(within(form).queryByLabelText("Invite with handling code C")).toBeNull();
    expect(within(form).queryByLabelText("Invite with handling code R")).toBeNull();
  });

  it("offers no clearance to an inviter whose own is outside the scheme: Invite cannot be pressed, and it says why", async () => {
    const posted = serve("outside");
    const form = await open([]);
    await waitFor(() => expect(form.textContent).toContain("which is not one of this deployment's classifications"));
    expect((within(form).getByRole("button", { name: "Invite" }) as HTMLButtonElement).disabled).toBe(true);
    expect(form.textContent).toContain(
      "You hold TOP-SECRET, which is not one of this deployment's classifications, so you cannot give any clearance and nobody can be invited by you.",
    );
    expect(form.textContent).not.toContain("you can give that clearance or lower");
    expect(posted).toEqual([]);
  });

  it("gives no level to a clearance outside the scheme, and no handling code they do not hold (the filters themselves)", () => {
    expect(givableLevels(ORDER, { clearance: "TOP-SECRET", codes: [] })).toEqual([]);
    expect(givableLevels(ORDER, { clearance: "OFFICIAL", codes: [] })).toEqual(["PUBLIC", "OFFICIAL"]);
    expect(givableCodes(["P", "C", "R"], { clearance: "OFFICIAL", codes: ["P", "X"] })).toEqual(["P"]);
  });
});

describe("the form is drawn only once the inviter's own details have arrived", () => {
  const mustNotBeUsable = () => {
    expect(screen.queryByRole("form", { name: "Invite a person" })).toBeNull();
    expect(screen.queryByLabelText("Invite clearance")).toBeNull();
    expect(screen.queryByLabelText(/^Invite with handling code/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Invite" })).toBeNull();
    expect(screen.queryByLabelText("Sign-in name")).toBeNull();
  };

  it("has no clearance select, handling-code box or Invite button while waiting, and says it is reading; then offers them", async () => {
    let release: () => void = () => {};
    serve("own", new Promise<void>((resolve) => (release = resolve)));
    render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(["manage_people"])} />);
    const waiting = await screen.findByRole("status");
    expect(waiting.textContent).toContain("Reading what you can give");
    await waitFor(() => expect(screen.getByLabelText("Edit access for ana")).toBeTruthy()); // the section has loaded around it
    mustNotBeUsable();
    release();
    const form = await screen.findByRole("form", { name: "Invite a person" });
    await waitFor(() => expect(optionNames(form)).toEqual(["PUBLIC", "OFFICIAL"]));
    expect(screen.queryByText(/Reading what you can give/)).toBeNull();
  });

  it("has none of them when GET /v1/me does not answer, and says in words that nobody can be invited from here", async () => {
    const posted = serve("down");
    render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(["manage_people"])} />);
    const words = await screen.findByRole("alert");
    expect(words.textContent).toContain("Your own clearance and handling codes could not be read, so nobody can be invited from here now.");
    expect(words.textContent).toContain("Reload the page to try again.");
    await waitFor(() => expect(screen.getByLabelText("Edit access for ana")).toBeTruthy());
    mustNotBeUsable();
    expect(posted).toEqual([]);
  });

  it("has none of them when GET /v1/me answers something that is not an inviter", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const path = new URL(url).pathname.replace("/v1/admin/", "");
        if (path === "/v1/me") return json(200, { unexpected: true });
        if (path === "people") return json(200, [ANA]);
        if (path === "/v1/handling-scheme") return json(200, SCHEME);
        if (path === "people/rows") return json(200, { rows: [], without_author: [] });
        if (path === "roles") return json(200, { built_in: [], custom: [] });
        if (path === "sign-in") return json(200, { kind: "keycloak" });
        return json(200, path === "organisation-arrivals" ? [] : {});
      }),
    );
    render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(["manage_people"])} />);
    expect((await screen.findByRole("alert")).textContent).toContain("could not be read");
    mustNotBeUsable();
  });
});

describe("a refused invitation is said by the Invite button, as an error summary", () => {
  const fill = (form: HTMLElement) => {
    fireEvent.change(within(form).getByLabelText("Sign-in name"), { target: { value: "new.person" } });
    fireEvent.change(within(form).getByLabelText("Invite unit"), { target: { value: "unit-1" } });
  };

  it.each([
    ["a clearance above the inviter's own",
     (form: HTMLElement) => fireEvent.change(within(form).getByLabelText("Invite clearance"), { target: { value: "OFFICIAL-SENSITIVE" } }),
     "You cannot give a clearance above your own (OFFICIAL-SENSITIVE asked)."],
    ["a handling code the inviter cannot receive",
     (form: HTMLElement) => fireEvent.click(within(form).getByLabelText("Invite with handling code C")),
     "You cannot give a handling code you do not hold yourself (C)."],
  ])("for %s: beside the button, in words, with focus on it", async (_what, choose, words) => {
    const posted = serve("stale");
    const form = await open(ORDER);
    fill(form);
    choose(form);
    fireEvent.click(within(form).getByRole("button", { name: "Invite" }));

    const summary = await within(form).findByRole("alert");
    expect(posted).toHaveLength(1); // it was asked, and the route refused it
    expect(summary.textContent).toContain("There is a problem");
    expect(summary.textContent).toContain(words);
    // Beside the button: directly before it, and after every field, not above them in the intro.
    const button = within(form).getByRole("button", { name: "Invite" });
    expect(summary.nextElementSibling).toBe(button);
    const lastField = within(form).getByLabelText("Invite as Analyst");
    expect(lastField.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(form).getAllByRole("alert")).toHaveLength(1); // said once, not also above the fields
    // Focus goes to it (a summary is focusable by script, not a Tab stop).
    await waitFor(() => expect(document.activeElement).toBe(summary));
    expect(summary.getAttribute("tabindex")).toBe("-1");
    expect(screen.queryByText("ABCD-EFGH-JKLM-NPQR")).toBeNull();
  });

  it("is gone when the invitation is sent again and accepted", async () => {
    serve("stale");
    const form = await open(ORDER);
    fill(form);
    fireEvent.change(within(form).getByLabelText("Invite clearance"), { target: { value: "OFFICIAL-SENSITIVE" } });
    fireEvent.click(within(form).getByRole("button", { name: "Invite" }));
    await within(form).findByRole("alert");
    fireEvent.change(within(form).getByLabelText("Invite clearance"), { target: { value: "OFFICIAL" } });
    fireEvent.click(within(form).getByRole("button", { name: "Invite" }));
    expect(await screen.findByText("ABCD-EFGH-JKLM-NPQR")).toBeTruthy();
    expect(within(form).queryByRole("alert")).toBeNull();
  });
});
