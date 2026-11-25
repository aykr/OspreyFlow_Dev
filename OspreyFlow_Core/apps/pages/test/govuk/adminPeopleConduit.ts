/**
 * A fixture Conduit for the Admin People page (slice AD3a): a real HTTP server on a free port that RECORDS every call and REFUSES what the
 * real routes refuse (rule 15: a fixture that only grants proves the page agrees with our hopes). Synthetic throughout (rule 9).
 *
 * What it refuses, as `services/api/app.py` does:
 *  - every `/v1` route: no `Authorization: Bearer`, or a bearer it does not know, is 401 `{"detail": "Not authenticated"}`; a token in the
 *    query is ignored, so refused as missing;
 *  - `GET /v1/admin/people`, `GET /v1/admin/people/rows` and `GET /v1/admin/roles` are behind `require_right(Right.MANAGE_PEOPLE)`, checked
 *    before anything else the route does: a person without it is 403 `{"detail": {"error": "right_required", "right": "manage_people"}}`
 *    (the Conduit's words name the right, so the page must never show them);
 *  - a method a route does not serve is 405 `{"detail": "Method Not Allowed"}`, and a route it has not is 404 `{"detail": "Not Found"}`, both
 *    before the bearer is looked at (the router answers first).
 * What it sends, as the route's models do: `PersonAccount` for each person, and `RolesCatalogue` (`built_in`, `custom`) for the roles.
 * A test can make it fail (`people`, `roles`) to show what the page does with a Conduit that does.
 */
import { createServer } from "node:http";
import type { IncomingHttpHeaders, Server } from "node:http";
import type { AddressInfo } from "node:net";

export interface Reader {
  /** The bearer this person's sessions carry. */
  token: string;
  rights: string[];
}

export interface Account {
  id: string;
  username: string;
  name: string;
  enabled: boolean;
  roles: string[];
  clearance?: string | null;
  org_unit?: string | null;
  must_set_password?: boolean;
  system_account?: boolean;
  organisation_linked?: boolean;
}

/** What a call to the fixture saw: the headers a browser's request would add are in `headers`, so that a test can show none came. */
export interface Call {
  method: string;
  /** The path and the query, as received. */
  url: string;
  headers: IncomingHttpHeaders;
}

/** A canned answer in place of the route's own: `status` and `body` (JSON, or text when it is a string). */
export interface Canned {
  status: number;
  body: unknown;
}

export interface AdminConduitOptions {
  readers: Reader[];
  people: Account[];
  /** The roles catalogue's custom roles; the built-in roles are the real ones' ids and labels. */
  custom?: { id: string; name: string }[];
  /** A failing or odd answer for the people route, given to a reader who holds the right. */
  people_answer?: Canned;
  /** The same for the roles route. */
  roles_answer?: Canned;
}

export interface AdminConduit {
  url: string;
  calls: Call[];
  stop(): Promise<void>;
}

/** The labels the real catalogue gives the built-in roles (`BUILT_IN_ROLE_LABELS` in `services/api/app.py`). */
export const BUILT_IN = [
  { id: "analyst", label: "Analyst" },
  { id: "data_engineer", label: "Data Engineer" },
  { id: "osprey-admin", label: "Admin" },
  { id: "reports_viewer", label: "Reports Viewer" },
  { id: "rule_author", label: "Rule author" },
  { id: "super_user", label: "Super user" },
] as const;

/** The right the three routes ask for, and the refusal's body, as `require_right` words it. */
export const MANAGE_PEOPLE = "manage_people";
export const REFUSAL = { detail: { error: "right_required", right: MANAGE_PEOPLE } };

/** A person, as `PersonAccount` has them: the fields not named take the model's defaults. */
export function account(over: Partial<Account> & Pick<Account, "id" | "username" | "name">): Account {
  return { enabled: true, roles: [], clearance: null, org_unit: null, must_set_password: false, system_account: false, organisation_linked: false, ...over };
}

export async function adminConduit(options: AdminConduitOptions): Promise<AdminConduit> {
  const calls: Call[] = [];
  const server: Server = createServer((req, res) => {
    const url = req.url ?? "/";
    calls.push({ method: req.method ?? "", url, headers: req.headers });
    const send = (status: number, body: unknown): void => {
      res.statusCode = status;
      if (typeof body === "string") {
        res.setHeader("Content-Type", "text/plain");
        res.end(body);
        return;
      }
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(body));
    };
    const path = url.split("?")[0] ?? "";
    const served: Record<string, () => void> = {
      "/v1/admin/people": () => send(options.people_answer?.status ?? 200, options.people_answer?.body ?? options.people),
      "/v1/admin/people/rows": () => send(200, { rows: [], without_author: [] }),
      "/v1/admin/roles": () =>
        send(options.roles_answer?.status ?? 200, options.roles_answer?.body ?? {
          built_in: BUILT_IN.map((role) => ({ ...role, rights: [], gives: [] })),
          custom: (options.custom ?? []).map((role) => ({ ...role, version: 1, rights: [], changed_by: "someone", changed_at: "2026-11-01T09:00:00Z", holders: 0, team: null })),
        }),
    };
    // The router answers first, as FastAPI's does: a route it has not is 404 and a method the route does not serve is 405, for anyone.
    const route = served[path];
    if (!route) return send(404, { detail: "Not Found" });
    if (req.method !== "GET") return send(405, { detail: "Method Not Allowed" });
    // Then the route's dependencies, in order: who the bearer is, and the right, before the route does anything else.
    const header = req.headers["authorization"];
    const token = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : undefined;
    const reader = options.readers.find((r) => r.token === token);
    if (!reader) return send(401, { detail: "Not authenticated" });
    if (!reader.rights.includes(MANAGE_PEOPLE)) return send(403, REFUSAL);
    route();
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  return {
    url: `http://127.0.0.1:${port}`,
    calls,
    stop: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}
