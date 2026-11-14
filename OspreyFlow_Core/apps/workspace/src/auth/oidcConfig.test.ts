// @vitest-environment jsdom
//
// ADR-114 Amendment 4 decision 5: the Glass learns its identity provider at run time, from the
// deployment's `/deployment.json`, so one bundle serves every deployment. Where the file is absent
// (the Vite development server answers every path with the page) the development default stands.
import { afterEach, describe, expect, it } from "vitest";

import {
  deploymentAppearance,
  deploymentMarking,
  deploymentReportsUrl,
  deploymentWelcome,
  loadDeploymentSettings,
  oidcAuthority,
  oidcClientId,
  oidcScope,
  resetDeploymentSettings,
} from "./oidcConfig";

function answering(status: number, body: string): typeof fetch {
  return (async () => new Response(body, { status })) as typeof fetch;
}

describe("the identity provider's address", () => {
  afterEach(() => resetDeploymentSettings());

  it("is the deployment's own, read at run time", async () => {
    await loadDeploymentSettings(
      answering(
        200,
        JSON.stringify({
          identity_provider: "http://id.osprey.test:8443/",
          realm: "osprey",
        }),
      ),
    );
    expect(oidcAuthority()).toBe("http://id.osprey.test:8443/realms/osprey");
  });

  it("is never the build-time port when the deployment names one", async () => {
    await loadDeploymentSettings(
      answering(
        200,
        JSON.stringify({
          identity_provider: "http://id.ospreyflow.localhost",
          realm: "osprey",
        }),
      ),
    );
    expect(oidcAuthority()).not.toContain(":8081");
  });

  it("falls back to the development default when there is no file", async () => {
    await loadDeploymentSettings(answering(404, "not found"));
    expect(oidcAuthority()).toBe(
      `${window.location.protocol}//${window.location.hostname}:8081/realms/osprey`,
    );
    await loadDeploymentSettings(
      answering(200, "<!doctype html><title>the Glass</title>"),
    );
    expect(oidcAuthority()).toContain(":8081/realms/osprey");
  });
});

// ADR-115 decision 2: the marking a surface with no case data shows comes with the deployment.
describe("the deployment's marking", () => {
  afterEach(() => resetDeploymentSettings());

  it("is read with the identity provider", async () => {
    await loadDeploymentSettings(
      answering(200, JSON.stringify({ identity_provider: "http://id.osprey.test", realm: "osprey", marking: "OFFICIAL" })),
    );
    expect(deploymentMarking()).toBe("OFFICIAL");
  });

  it("is unknown where there is no deployment file", async () => {
    await loadDeploymentSettings(answering(404, "not found"));
    expect(deploymentMarking()).toBeNull();
  });
});

// ADR-115 decisions 3 and 8: what the welcome page offers comes with the deployment.
describe("the deployment's welcome settings", () => {
  afterEach(() => resetDeploymentSettings());

  it("are read with the identity provider", async () => {
    await loadDeploymentSettings(
      answering(
        200,
        JSON.stringify({
          identity_provider: "http://id.osprey.test",
          realm: "osprey",
          organisation_sign_in: "acme-entra",
          // ADR-115 Amendment 5: the provider's name, as the answers gave it.
          organisation_label: "Example Department account",
          welcome: {
            about: false,
            // A known name with a script address, and an unknown name: neither is ever a link.
            links: { privacy: "https://privacy.test/", accessibility: "javascript:alert(1)", evil: "https://x.test/" },
          },
          version: "c01833b",
        }),
      ),
    );
    expect(deploymentWelcome()).toEqual({
      organisationSignIn: "acme-entra",
      organisationLabel: "Example Department account",
      about: false,
      links: { privacy: "https://privacy.test/" },
      version: "c01833b",
    });
  });

  it("are the plain page where there is no deployment file", async () => {
    await loadDeploymentSettings(answering(404, "not found"));
    expect(deploymentWelcome()).toEqual({
      organisationSignIn: null,
      organisationLabel: null,
      about: true,
      links: {},
      version: null,
    });
  });

  it("read no label where the deployment gives none, or one that is not words", async () => {
    for (const label of [undefined, "", 42, "   "]) {
      resetDeploymentSettings();
      await loadDeploymentSettings(
        answering(
          200,
          JSON.stringify({ identity_provider: "http://id.osprey.test", organisation_sign_in: "org", organisation_label: label }),
        ),
      );
      expect(deploymentWelcome().organisationLabel).toBeNull();
    }
  });
});

// ADR-132: the deployment's brand travels in the same file, so one bundle serves every deployment.
describe("the deployment's appearance", () => {
  afterEach(() => resetDeploymentSettings());

  it("is read with the identity provider", async () => {
    await loadDeploymentSettings(
      answering(
        200,
        JSON.stringify({
          identity_provider: "http://id.osprey.test",
          appearance: { brand: "govuk", service_name: "Prison Intelligence", organisation: "Ministry of Examples", phase: "beta" },
        }),
      ),
    );
    expect(deploymentAppearance()).toEqual({
      brand: "govuk",
      serviceName: "Prison Intelligence",
      organisation: "Ministry of Examples",
      phase: "beta",
    });
  });

  it("is the OspreyFlow brand where there is no deployment file", async () => {
    await loadDeploymentSettings(answering(404, "not found"));
    expect(deploymentAppearance()).toEqual({ brand: "ospreyflow", serviceName: null, organisation: null, phase: "none" });
  });
});

// The owner's ruling of 13 November 2026 (Q2): "Build a report" opens Superset at the address the
// deployment gives, and is offered only where there is one.
describe("Superset's address, for Build a report", () => {
  afterEach(() => resetDeploymentSettings());

  it("is read with the identity provider", async () => {
    await loadDeploymentSettings(
      answering(200, JSON.stringify({ identity_provider: "http://id.osprey.test", reports_url: "https://bi.osprey.test" })),
    );
    expect(deploymentReportsUrl()).toBe("https://bi.osprey.test");
  });

  it.each([
    ["no Superset", {}],
    ["not a web address", { reports_url: "javascript:alert(1)" }],
    ["a path, not an origin", { reports_url: "https://bi.osprey.test/login" }],
    ["not a string", { reports_url: 7 }],
  ])("is none for %s, so the link is not offered", async (_case, extra) => {
    await loadDeploymentSettings(answering(200, JSON.stringify({ identity_provider: "http://id.osprey.test", ...extra })));
    expect(deploymentReportsUrl()).toBeNull();
  });

  it("is none where there is no deployment file", async () => {
    await loadDeploymentSettings(answering(404, "not found"));
    expect(deploymentReportsUrl()).toBeNull();
  });
});

// ADR-148 Amendment 8: Entra ID's authority, the Glass's app registration and this API's scope, read from the
// deployment's file only when it names Entra; Keycloak's sign-in is exactly as it was.
describe("the sign-in on Entra ID", () => {
  afterEach(() => resetDeploymentSettings());
  const TENANT = "00000000-1111-4222-8333-444444444444";
  const ENTRA = {
    kind: "entra",
    authority: `https://login.microsoftonline.com/${TENANT}/v2.0`,
    client_id: "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff",
    scope: "openid profile api://aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/access_as_user",
  };

  it("is Entra's authority, the Glass's registration and this API's scope", async () => {
    await loadDeploymentSettings(answering(200, JSON.stringify({ sign_in: ENTRA, marking: "OFFICIAL" })));
    expect([oidcAuthority(), oidcClientId(), oidcScope()]).toEqual([ENTRA.authority, ENTRA.client_id, ENTRA.scope]);
    expect(deploymentMarking()).toBe("OFFICIAL");
  });

  it("is Keycloak's, exactly as before, when the file names no Entra sign-in", async () => {
    await loadDeploymentSettings(
      answering(200, JSON.stringify({ identity_provider: "https://id.osprey.test", realm: "osprey" })),
    );
    expect([oidcAuthority(), oidcClientId(), oidcScope()]).toEqual(["https://id.osprey.test/realms/osprey", "osprey-glass", "openid"]);
  });

  it.each([
    ["another kind", { ...ENTRA, kind: "keycloak" }],
    ["an authority that is not Entra's", { ...ENTRA, authority: "https://login.example.test/x/v2.0" }],
    ["no client", { ...ENTRA, client_id: "" }],
    ["no scope", { ...ENTRA, scope: undefined }],
  ])("is not taken from %s", async (_why, signIn) => {
    await loadDeploymentSettings(
      answering(200, JSON.stringify({ identity_provider: "https://id.osprey.test", realm: "osprey", sign_in: signIn })),
    );
    expect([oidcAuthority(), oidcClientId(), oidcScope()]).toEqual(["https://id.osprey.test/realms/osprey", "osprey-glass", "openid"]);
  });
});
