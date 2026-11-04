// @vitest-environment jsdom
//
// ADR-114 Amendment 4 decision 5: the Glass learns its identity provider at run time, from the
// deployment's `/deployment.json`, so one bundle serves every deployment. Where the file is absent
// (the Vite development server answers every path with the page) the development default stands.
import { afterEach, describe, expect, it } from "vitest";

import {
  deploymentAppearance,
  deploymentMarking,
  deploymentWelcome,
  loadDeploymentSettings,
  oidcAuthority,
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
