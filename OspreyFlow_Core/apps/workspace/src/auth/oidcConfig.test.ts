// @vitest-environment jsdom
//
// ADR-114 Amendment 4 decision 5: the Glass learns its identity provider at run time, from the
// deployment's `/deployment.json`, so one bundle serves every deployment. Where the file is absent
// (the Vite development server answers every path with the page) the development default stands.
import { afterEach, describe, expect, it } from "vitest";

import {
  deploymentMarking,
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
