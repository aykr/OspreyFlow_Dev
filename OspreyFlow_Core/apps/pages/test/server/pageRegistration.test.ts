/**
 * Slice IS5a0, round 2: the start-up refusals of the route-module convention hold for what Express treats as one route,
 * not only for byte-identical strings. Express (router 2.x) matches a route ignoring case and an optional trailing slash, so
 * `/studio` and `/Studio/` are one route and the later page would never be reached; `/Healthz` is answered by the health
 * route before any page. The planted shapes are the ones `createApp` is really given: a page list with a path each.
 */
import { describe, expect, it } from "vitest";

import { build } from "../support/build.js";
import { fixturePage } from "../fixtures/pages.js";
import { request } from "../support/http.js";
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
