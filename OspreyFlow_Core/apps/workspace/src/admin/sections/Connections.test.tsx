// @vitest-environment jsdom
// ADR-140 Amendments 4, 13 and 15 (L2.7): the Admin area's Connections. Red if the tab shows to
// someone without administer_system; if a connection named here never reaches the route; if a SQL or
// API connection is sent without its datasets or with anything but its secret's name; if a value
// typed into a secret's field is sent at all; or if Test connection does not reach its route.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPlace } from "../AdminPlace";
import { CLOUD_ROLE_TIP, SECRET_TIP } from "./Connections";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const FILES = { id: "files", kind: "files", name: "Files: the ingest root", created_by: "system", created_at: "" };
const TELCO = {
  id: "c-api", kind: "api", name: "Telco lookup (synthetic)", created_by: "adm-1", created_at: "", datasets: ["ds-a"],
  settings: { kind: "api", base_url: "https://telco.example", auth: "bearer", secret: "TELCO", pagination: "none" },
}; // prettier-ignore
const DATASETS = [
  { id: "ds-a", name: "Prison records", owning_unit: "u", egress: "none", kind: "source", promotion_policy: "author_promotes" },
  { id: "ds-b", name: "Carrier records", owning_unit: "u", egress: "none", kind: "source", promotion_policy: "author_promotes" },
]; // prettier-ignore
const PASTED = "synthetic-telco-secret-9f3a";

function serve(listed: unknown[] = [FILES]) {
  const posts: { path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(String(url)).pathname;
      const json = (status: number, body: unknown) => ({ ok: status < 400, status, json: async () => body }) as Response;
      if (init?.method === "POST") posts.push({ path, body: init.body ? JSON.parse(String(init.body)) : null });
      if (path === "/v1/admin/connections" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { name: string; kind: string };
        return json(201, { ...FILES, ...body, id: "c2", created_by: "adm-1" });
      }
      if (path === "/v1/admin/connections/c-api/test") return json(200, { ok: true, words: "The host is allowed and the secret is set." });
      if (path === "/v1/admin/connections") return json(200, listed);
      if (path === "/v1/admin/datasets") return json(200, DATASETS);
      return json(200, []);
    }),
  );
  return posts;
}

function open() {
  render(<AdminPlace apiBaseUrl="http://api" bearerToken="t" rights={new Set(["administer_system"])} />);
  fireEvent.click(screen.getByRole("button", { name: "Connections" }));
}

const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe("Connections", () => {
  it("is a tab for administer_system alone, lists the built-in Files, and names a new one", async () => {
    const posts = serve();
    render(<AdminPlace apiBaseUrl="http://api" bearerToken="t" rights={new Set(["operate_schedules"])} />);
    expect(screen.queryByRole("button", { name: "Connections" })).toBeNull();
    cleanup();
    open();
    expect(await screen.findByText("Files: the ingest root")).toBeTruthy();
    expect(screen.getByText("built in")).toBeTruthy();
    type("Connection name", "Second folder");
    fireEvent.click(screen.getByRole("button", { name: "Name the connection" }));
    await waitFor(() => expect(posts).toEqual([{ path: "/v1/admin/connections", body: { kind: "files", name: "Second folder" } }]));
    expect(await screen.findByText("Named Second folder.")).toBeTruthy();
  });

  it("names a SQL connection with its datasets and its secret by name, and nothing else", async () => {
    const posts = serve();
    open();
    await screen.findByText("Files: the ingest root");
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "sql" } });
    type("Connection name", "Client replica (synthetic)");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Prison records" }));
    type("Host", "replica.client.example");
    type("Database", "nomis");
    type("Read-only login", "osprey_reader");
    type("Secret's name (the login's password)", "NOMIS_REPLICA");
    const secret = screen.getByLabelText("Secret's name (the login's password)");
    expect(document.getElementById(secret.getAttribute("aria-describedby")!)?.textContent).toBe(SECRET_TIP);
    fireEvent.click(screen.getByRole("button", { name: "Name the connection" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]!.body).toEqual({
      kind: "sql", name: "Client replica (synthetic)", datasets: ["ds-a"],
      settings: { kind: "sql", host: "replica.client.example", port: 5432, database: "nomis", user: "osprey_reader",
                  secret: "NOMIS_REPLICA", tls: "verify-full", schemas: ["public"] },
    }); // prettier-ignore
  });

  it("never sends a secret's field holding anything but a name, which may be the value itself", async () => {
    const posts = serve();
    open();
    await screen.findByText("Files: the ingest root");
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "api" } });
    type("Connection name", "Telco lookup (synthetic)");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Prison records" }));
    type("Base URL", "https://telco.example");
    fireEvent.change(screen.getByLabelText("Sign-in"), { target: { value: "bearer" } });
    type("Secret's name (the token)", PASTED);
    fireEvent.click(screen.getByRole("button", { name: "Name the connection" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/never the password or token itself/);
    expect(posts).toEqual([]);
    expect(screen.getByRole("alert").textContent).not.toContain(PASTED);
  });

  it("refuses a SQL or API connection bound to no dataset, before sending it", async () => {
    const posts = serve();
    open();
    await screen.findByText("Files: the ingest root");
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "json" } });
    type("Connection name", "Exports (synthetic)");
    fireEvent.click(screen.getByRole("button", { name: "Name the connection" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Choose the datasets whose sources may read through it.");
    expect(posts).toEqual([]);
  });

  // L1.9 (ADR-148): an S3 bucket and Athena are read as the deployment's own cloud role. Red if either
  // form offers a field a key or secret could be typed into, or sends one; if a dotted bucket (which
  // cannot be reached by its own name over verified TLS) is sent; or if the role's words are missing.
  it("names an S3 bucket and Athena with no field for a key or a secret, and sends none", async () => {
    const posts = serve();
    open();
    await screen.findByText("Files: the ingest root");
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "s3" } });
    expect(screen.queryByLabelText(/secret|key|password|token/i)).toBeNull();
    expect(document.getElementById(screen.getByLabelText("Region").getAttribute("aria-describedby")!)?.textContent).toBe(
      CLOUD_ROLE_TIP,
    );
    type("Connection name", "Client exports (synthetic)");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Prison records" }));
    type("Bucket", "client.exports");
    fireEvent.click(screen.getByRole("button", { name: "Name the connection" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/with no dot/);
    expect(posts).toEqual([]);
    type("Bucket", "synthetic-exports");
    type("Folder sources may read under (empty for the whole bucket)", "client-a/");
    fireEvent.click(screen.getByRole("button", { name: "Name the connection" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]!.body).toEqual({
      kind: "s3", name: "Client exports (synthetic)", datasets: ["ds-a"],
      settings: { kind: "s3", region: "eu-west-2", bucket: "synthetic-exports", prefix: "client-a/" },
    }); // prettier-ignore

    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "athena" } });
    expect(screen.queryByLabelText(/secret|key|password|token/i)).toBeNull();
    type("Connection name", "Client Athena (synthetic)");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Prison records" }));
    type("Databases a source may read (comma-separated)", "visits, calls");
    // The catalog (09 §2; the orchestrator's review of L1.9, round 1, item 8): Athena's own by default,
    // a client's own when named, and a name Athena would not take refused before it is sent.
    expect((screen.getByLabelText("Catalog") as HTMLInputElement).value).toBe("AwsDataCatalog");
    type("Catalog", "client catalog");
    fireEvent.click(screen.getByRole("button", { name: "Name the connection" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/catalog's name/);
    expect(posts).toHaveLength(1);
    type("Catalog", "client_catalog");
    fireEvent.click(screen.getByRole("button", { name: "Name the connection" }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1]!.body).toEqual({
      kind: "athena", name: "Client Athena (synthetic)", datasets: ["ds-a"],
      settings: { kind: "athena", region: "eu-west-2", workgroup: "primary", catalog: "client_catalog",
                  databases: ["visits", "calls"] },
    }); // prettier-ignore
  });

  it("lists what a connection reads, its secret's name, its datasets by name, and tests it", async () => {
    const posts = serve([FILES, TELCO]);
    open();
    const row = (await screen.findByText("Telco lookup (synthetic)")).closest("tr")!;
    await waitFor(() => expect(within(row).getByText("Prison records")).toBeTruthy());
    expect(within(row).getByText("https://telco.example")).toBeTruthy();
    expect(within(row).getByText("TELCO")).toBeTruthy();
    fireEvent.click(within(row).getByRole("button", { name: "Test connection: Telco lookup (synthetic)" }));
    expect((await within(row).findByRole("status")).textContent).toBe("✓ The host is allowed and the secret is set.");
    expect(posts.map((p) => p.path)).toEqual(["/v1/admin/connections/c-api/test"]);
  });
});
