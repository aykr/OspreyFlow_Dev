/**
 * Slice GR2a, round 2 (the end of this file): the registration rules for a service with two trees. Which test fails if the rule is
 * broken (rule 12), each shown red by planting the fault at `server/pages.ts` / `server/app.ts` (rule 15):
 *  - the throw for a page whose `trees` is empty deleted                                              -> "names no tree"
 *  - the throw for a page naming a tree the service does not have deleted                             -> "does not have"
 *  - `check` made one whole-list check (a Default and a GOV.UK twin then refuse each other)           -> "twin"
 *  - `checkTree` filtered to the Default tree (two GOV.UK pages could then claim one path or id)       -> "two pages on one path in the GOV.UK tree"
 *  - the `servedBy` filter on the upload paths (app.ts) left out                                      -> "upload"
 *
 * Slice IS5a0, round 2: the start-up refusals of the route-module convention hold for what Express treats as one route,
 * not only for byte-identical strings. Express (router 2.x) matches a route ignoring case and an optional trailing slash, so
 * `/studio` and `/Studio/` are one route and the later page would never be reached; `/Healthz` is answered by the health
 * route before any page. The planted shapes are the ones `createApp` is really given: a page list with a path each.
 */
import { describe, expect, it } from "vitest";

import { build } from "../support/build.js";
import { fixturePage } from "../fixtures/pages.js";
import { request, signIn } from "../support/http.js";
import type { PageModule } from "../../server/pages.js";
import { join } from "node:path";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const FIXTURE_VIEWS = [join(dirname(fileURLToPath(import.meta.url)), "..", "fixtures", "views")];

function served(pages: ReturnType<typeof fixturePage>[]) {
  return build({ pages, viewDirs: FIXTURE_VIEWS, functionIds: new Set(pages.map((page) => page.id)) });
}

describe("two modules on what Express treats as one route", () => {
  const a = { ...fixturePage(), id: "studio-frame", path: "/studio" };
  const other = (path: string) => ({ ...fixturePage(), id: "studio-releases", path });

  it("the premise: Express answers a differently cased or slashed request from the one route", async () => {
    const { app } = served([a]);
    for (const path of ["/studio", "/Studio", "/STUDIO/", "/studio/"]) {
      const res = await request(app).get(path);
      expect(res.status, path).toBe(302); // the page's session check ran: the route matched
      expect(res.headers["location"], path).toBe("/session/sign-in");
    }
  });

  it.each(["/Studio", "/STUDIO", "/studio/", "/Studio/"])("refuses a second page at %s, in words, as the same path", (path) => {
    expect(() => served([a, other(path)]), path).toThrow(/path/i);
  });

  it("accepts two different plain paths (the refusal is not a blanket one)", () => {
    expect(() => served([a, other("/studio-releases")])).not.toThrow();
  });

  it.each(["/Healthz", "/HEALTHZ", "/SESSION/sign-in", "/Session", "/healthz/", "/session/", "/V1/x", "/Assets/pages/x", "/assets/pages/"])(
    "refuses %s as a path the server answers itself",
    (path) => {
      expect(() => served([{ ...a, path }]), path).toThrow(new RegExp(path.replace(/[/.]/g, "\\$&"), "i"));
    },
  );
});

describe("the registration rules of a service with two trees (slice GR2a)", () => {
  const text = (words: string): PageModule["handler"] => (_req, res) => void res.type("text/plain").send(words);
  // Both pages are real rows of the real FUNCTIONS.yaml, as `createApp` is given them; no `functionIds` override.
  const base = { methods: ["GET"] as const, id: "studio-frame", path: "/twin" };
  const real = (pages: readonly PageModule[], tree?: "default" | "govuk") =>
    build({ pages, ...(tree ? { tree } : {}), viewDirs: FIXTURE_VIEWS, functionIds: new Set(["studio-frame", "studio-releases", "help"]) });

  it("a page whose `trees` is empty is refused at start, in words (never a page no tree serves)", () => {
    const page: PageModule = { ...base, trees: [], handler: text("x") };
    expect(() => real([page])).toThrow(/studio-frame.*\/twin.*names no tree/s);
    expect(() => real([page])).toThrow(/default or govuk/);
    // The control: the same page naming a tree, and the same page naming none (the Default tree's), are accepted.
    expect(() => real([{ ...page, trees: ["govuk"] }])).not.toThrow();
    const { trees: _none, ...plain } = page;
    expect(() => real([plain])).not.toThrow();
  });

  it("a page naming a tree the service does not have is refused, in words, whether or not another tree is named too", () => {
    for (const trees of [["civic"], ["govuk", "civic"]] as unknown as (readonly ("default" | "govuk")[])[]) {
      const page: PageModule = { ...base, trees, handler: text("x") };
      expect(() => real([page]), trees.join()).toThrow(/studio-frame.*"civic".*which the service does not have/s);
    }
  });

  it("twin: a Default page and a GOV.UK page may share an id and a path, and each tree serves its own", async () => {
    const defaultTwin: PageModule = { ...base, trees: ["default"], handler: text("the default page") };
    const govukTwin: PageModule = { ...base, trees: ["govuk"], handler: text("the govuk page") };
    for (const [tree, words] of [["default", "the default page"], ["govuk", "the govuk page"]] as const) {
      const { app } = real([defaultTwin, govukTwin], tree);
      const who = await signIn(app);
      const res = await request(app).get("/twin").set("Cookie", who.cookie);
      expect([res.status, res.text], tree).toEqual([200, words]);
    }
  });

  it("two pages on one path within the GOV.UK tree are refused, and so are two with one id; the Default tree's list is checked as well", () => {
    const one: PageModule = { ...base, trees: ["govuk"], handler: text("one") };
    expect(() => real([one, { ...one, id: "studio-releases" }])).toThrow(/two pages claim the path \/twin: studio-frame and studio-releases/);
    expect(() => real([one, { ...one, path: "/other" }])).toThrow(/the id studio-frame is used by more than one page/);
    // A page naming both trees is in both lists, so a GOV.UK page on its path is refused whichever tree it clashes in.
    const both: PageModule = { ...one, trees: ["default", "govuk"] };
    expect(() => real([both, { ...one, id: "studio-releases" }])).toThrow(/two pages claim the path \/twin/);
    // The same two, one in each tree, are the twins above: accepted.
    expect(() => real([one, { ...one, id: "studio-releases", trees: ["default"] }])).not.toThrow();
  });

  it("upload: a page's upload path is left to its own reader only in the tree that serves it", async () => {
    const reached = { count: 0 };
    const uploadPage: PageModule = {
      ...base,
      path: "/twin-upload",
      methods: ["GET", "POST"],
      upload: true,
      trees: ["govuk"],
      handler: (_req, res) => {
        reached.count += 1;
        res.status(202).type("text/plain").send("the page's own reader");
      },
    };
    const multipart = async (tree: "default" | "govuk") => {
      const { app } = real([uploadPage], tree);
      const who = await signIn(app);
      // A signed-in multipart POST carrying no token anywhere: the page's reader would be the one to refuse it.
      return request(app).post("/twin-upload").set("Cookie", who.cookie).attach("file", Buffer.from("x"), "x.txt");
    };
    // In the tree that serves it, the check is left to the reader (the handler is reached).
    expect((await multipart("govuk")).status).toBe(202);
    expect(reached.count).toBe(1);
    // In the other tree the page is not there, and its path is no upload path: the anti-forgery check refuses, as for any POST.
    const other = await multipart("default");
    expect(other.status).toBe(403);
    expect(other.text).toContain("could not be checked");
    expect(reached.count).toBe(1);
  });
});
