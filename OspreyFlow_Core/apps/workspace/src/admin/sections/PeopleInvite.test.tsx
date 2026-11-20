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
 * (`outside`); a 503 (`down`); or a network failure (`broken`). `live` is what the double answers *now*, so a test can change it between reads:
 * `me`; `scheme` ("ok", "down" for a 503, "broken" for a network failure, "bare" for an answer with no classifications);
 * `inviter` (details that replace the named ones). `meGate` / `schemeGate`: when given, that route answers only once the
 * promise resolves. `calls` counts the reads of each route. */
type Me = "own" | "stale" | "outside" | "down" | "broken";
type Live = { me: Me; scheme: "ok" | "down" | "broken" | "bare"; inviter?: object; calls: Record<string, number> };
const STALE = { ...INVITER, clearance: "OFFICIAL-SENSITIVE", receivable_handling_codes: ["P", "C", "R"] };
const OUTSIDE = { ...INVITER, clearance: "TOP-SECRET", receivable_handling_codes: [] };
let live: Live = { me: "own", scheme: "ok", calls: {} };

function serve(me: Me, gates: { meGate?: Promise<void>; schemeGate?: Promise<void>; scheme?: Live["scheme"] } = {}) {
  const posted: unknown[] = [];
  live = { me, scheme: gates.scheme ?? "ok", calls: {} };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      live.calls[path] = (live.calls[path] ?? 0) + 1;
      if (path === "/v1/me") {
        await gates.meGate;
        if (live.me === "broken") throw new TypeError("network down");
        return live.me === "down" ? json(503, {}) : json(200, live.inviter ?? { own: INVITER, stale: STALE, outside: OUTSIDE }[live.me]);
      }
      if (path === "/v1/handling-scheme") {
        await gates.schemeGate;
        if (live.scheme === "broken") throw new TypeError("network down");
        return live.scheme === "down" ? json(503, {}) : json(200, live.scheme === "bare" ? {} : SCHEME);
      }
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

  it("offers no clearance to an inviter whose own is outside the scheme: with the name and unit filled, nothing can be sent, and it says why", async () => {
    const posted = serve("outside");
    const form = await open([]);
    await waitFor(() => expect(form.textContent).toContain("which is not one of this deployment's classifications"));
    expect(form.textContent).toContain(
      "You hold TOP-SECRET, which is not one of this deployment's classifications, so you cannot give any clearance and nobody can be invited by you.",
    );
    expect(form.textContent).not.toContain("you can give that clearance or lower");
    // The name and the unit are filled, so the only thing left to stop Invite is that there is no clearance to give.
    fireEvent.change(within(form).getByLabelText("Sign-in name"), { target: { value: "new.person" } });
    fireEvent.change(within(form).getByLabelText("Invite unit"), { target: { value: "unit-1" } });
    const invite = within(form).getByRole("button", { name: "Invite" }) as HTMLButtonElement;
    expect((within(form).getByLabelText("Sign-in name") as HTMLInputElement).value).toBe("new.person");
    expect((within(form).getByLabelText("Invite unit") as HTMLInputElement).value).toBe("unit-1");
    expect(invite.disabled).toBe(true);
    fireEvent.click(invite);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(posted).toEqual([]);
  });

  it("gives no level to a clearance outside the scheme, and no handling code they do not hold (the filters themselves)", () => {
    expect(givableLevels(ORDER, { clearance: "TOP-SECRET", codes: [] })).toEqual([]);
    expect(givableLevels(ORDER, { clearance: "OFFICIAL", codes: [] })).toEqual(["PUBLIC", "OFFICIAL"]);
    expect(givableCodes(["P", "C", "R"], { clearance: "OFFICIAL", codes: ["P", "X"] })).toEqual(["P"]);
  });
});

describe("the form is drawn only when everything it depends on has loaded", () => {
  const SAYS_WHAT_THEY_CAN_GIVE = /You hold|that clearance or lower|no handling code|the handling codes/;
  const mustNotBeUsable = () => {
    expect(screen.queryByRole("form", { name: "Invite a person" })).toBeNull();
    expect(screen.queryByLabelText("Invite clearance")).toBeNull();
    expect(screen.queryByLabelText(/^Invite with handling code/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Invite" })).toBeNull();
    expect(screen.queryByLabelText("Sign-in name")).toBeNull();
    expect(screen.queryByLabelText("Invite unit")).toBeNull();
    expect(document.body.textContent).not.toMatch(SAYS_WHAT_THEY_CAN_GIVE);
  };
  const place = () => render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(["manage_people"])} />);
  const sectionLoaded = () => waitFor(() => expect(screen.getByLabelText("Edit access for ana")).toBeTruthy()); // the section has loaded around it
  const later = (ms = 30) => new Promise((resolve) => setTimeout(resolve, ms));

  /** Each thing the form reads before it offers a choice: how to hold its answer back, and how to make it fail. */
  const DEPENDENCIES = [
    {
      name: "the inviter's details (GET /v1/me)",
      late: (hold: Promise<void>) => serve("own", { meGate: hold }),
      fails: [
        ["with a 503", () => serve("down")],
        ["with a network failure", () => serve("broken")],
      ] as const,
      failure: "Your own clearance and handling codes could not be read, so nobody can be invited from here now.",
    },
    {
      name: "the handling scheme (GET /v1/handling-scheme)",
      late: (hold: Promise<void>) => serve("own", { schemeGate: hold }),
      fails: [
        ["with a 503", () => serve("own", { scheme: "down" })],
        ["with a network failure", () => serve("own", { scheme: "broken" })],
        ["with an answer that names no classifications", () => serve("own", { scheme: "bare" })],
      ] as const,
      failure: "This deployment's classifications and handling codes could not be read, so nobody can be invited from here now.",
    },
  ];

  describe.each(DEPENDENCIES)("$name", ({ late, fails, failure }) => {
    it("when late: says it is reading and has no select, box, field or Invite button; then draws the form once, correctly", async () => {
      let release: () => void = () => {};
      late(new Promise<void>((resolve) => (release = resolve)));
      place();
      const waiting = await screen.findByRole("status");
      expect(waiting.textContent).toContain("Reading what you can give");
      await sectionLoaded();
      await later();
      mustNotBeUsable();
      expect(screen.getByRole("status").textContent).toContain("Reading what you can give");
      release();
      const form = await screen.findByRole("form", { name: "Invite a person" });
      // Correct at its first draw, not after a second one.
      expect(optionNames(form)).toEqual(["PUBLIC", "OFFICIAL"]);
      expect(form.textContent).toContain("You hold OFFICIAL, so you can give that clearance or lower, and the handling codes P.");
      expect(within(form).getByLabelText("Invite with handling code P")).toBeTruthy();
      expect(within(form).queryByLabelText("Invite with handling code C")).toBeNull();
      expect(screen.queryByText(/Reading what you can give/)).toBeNull();
      // Drawn once: what is typed into it is still there, and it is the same form, a moment later.
      fireEvent.change(within(form).getByLabelText("Sign-in name"), { target: { value: "new.person" } });
      await later();
      expect(screen.getByRole("form", { name: "Invite a person" })).toBe(form);
      expect((within(form).getByLabelText("Sign-in name") as HTMLInputElement).value).toBe("new.person");
    });

    it.each(fails)("when it fails %s: says so in words and has no select, box, field or Invite button", async (_how, fail) => {
      const posted = fail();
      place();
      const words = await screen.findByRole("alert");
      expect(words.textContent).toContain(failure);
      expect(words.textContent).toContain("Reload the page to try again.");
      await sectionLoaded();
      await later();
      mustNotBeUsable();
      expect(screen.queryByText(/Reading what you can give/)).toBeNull();
      expect(posted).toEqual([]);
    });
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
    place();
    expect((await screen.findByRole("alert")).textContent).toContain("could not be read");
    mustNotBeUsable();
  });

  it("says a failure of one read even while the other is still late, and never offers a choice", async () => {
    serve("down", { schemeGate: new Promise<void>(() => {}) });
    place();
    expect((await screen.findByRole("alert")).textContent).toContain("could not be read");
    await sectionLoaded();
    mustNotBeUsable();
  });

  describe("after the form is drawn, the token changes and the reads run again", () => {
    const drawn = async () => {
      const view = render(<AdminPlace apiBaseUrl="http://x" bearerToken="t" rights={new Set(["manage_people"])} />);
      const form = await screen.findByRole("form", { name: "Invite a person" });
      await waitFor(() => expect(optionNames(form)).toEqual(["PUBLIC", "OFFICIAL"]));
      fireEvent.change(within(form).getByLabelText("Sign-in name"), { target: { value: "new.person" } });
      fireEvent.change(within(form).getByLabelText("Invite unit"), { target: { value: "unit-1" } });
      return { view, form };
    };
    const newToken = (view: ReturnType<typeof render>) =>
      view.rerender(<AdminPlace apiBaseUrl="http://x" bearerToken="t2" rights={new Set(["manage_people"])} />);
    const readAgain = async () => {
      await waitFor(() => {
        expect(live.calls["/v1/me"]).toBe(2);
        expect(live.calls["/v1/handling-scheme"]).toBe(2);
      });
      await later();
    };
    const same = (form: HTMLElement) => {
      expect(screen.getByRole("form", { name: "Invite a person" })).toBe(form);
      expect((within(form).getByLabelText("Sign-in name") as HTMLInputElement).value).toBe("new.person");
      expect((within(form).getByLabelText("Invite unit") as HTMLInputElement).value).toBe("unit-1");
    };

    it("keeps the drawn form, and what is typed in it, when the same details come back", async () => {
      serve("own");
      const { view, form } = await drawn();
      newToken(view);
      await readAgain();
      same(form);
      expect(optionNames(form)).toEqual(["PUBLIC", "OFFICIAL"]);
    });

    it.each([
      ["GET /v1/me fails", () => (live.me = "down")],
      ["GET /v1/handling-scheme fails", () => (live.scheme = "down")],
      ["both fail", () => ((live.me = "down"), (live.scheme = "broken"))],
    ])("keeps the drawn form, and what is typed in it, when %s: no could-not-be-read alert replaces it", async (_what, fail) => {
      serve("own");
      const { view, form } = await drawn();
      fail();
      newToken(view);
      await readAgain();
      same(form);
      expect(optionNames(form)).toEqual(["PUBLIC", "OFFICIAL"]);
      expect(screen.queryByText(/could not be read, so nobody can be invited/)).toBeNull();
    });

    it.each([
      ["a lower clearance", { ...INVITER, clearance: "PUBLIC" }, ["PUBLIC"], true],
      ["other handling codes", { ...INVITER, receivable_handling_codes: [] }, ["PUBLIC", "OFFICIAL"], false],
    ])("draws a fresh form when the details change to %s, so a choice already made is never quietly altered", async (_what, changed, offered, offersP) => {
      const posted = serve("own");
      const { view, form } = await drawn();
      fireEvent.change(within(form).getByLabelText("Invite clearance"), { target: { value: "OFFICIAL" } });
      fireEvent.click(within(form).getByLabelText("Invite with handling code P"));
      live.inviter = changed;
      newToken(view);
      await readAgain();
      const fresh = screen.getByRole("form", { name: "Invite a person" });
      expect(fresh).not.toBe(form);
      expect((within(fresh).getByLabelText("Sign-in name") as HTMLInputElement).value).toBe("");
      expect(optionNames(fresh)).toEqual(offered);
      // What it shows is what is sent: the clearance is the one now offered, and no code is ticked.
      fireEvent.change(within(fresh).getByLabelText("Sign-in name"), { target: { value: "new.person" } });
      fireEvent.change(within(fresh).getByLabelText("Invite unit"), { target: { value: "unit-1" } });
      fireEvent.click(within(fresh).getByRole("button", { name: "Invite" }));
      await waitFor(() => expect(posted).toHaveLength(1));
      expect(posted[0]).toMatchObject({ clearance: "PUBLIC", receivable_handling_codes: [] });
      expect(Boolean(within(fresh).queryByLabelText("Invite with handling code P"))).toBe(offersP);
    });
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
