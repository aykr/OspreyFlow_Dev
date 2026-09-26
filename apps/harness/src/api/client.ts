// `05_DEPLOYMENT.md` §2.3: "the UI never has a capability the headless path lacks." Every call
// here reaches exactly one of `harness/webapp.py`'s own routes — no client-side logic invents a
// capability the Python layer does not already expose. See that module's own docstring for the
// full UI→headless map this round's report cites.
import type { Consequences, OspreyConfig, ProfileOptions } from "./types";

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, body);
  }
  return (await response.json()) as T;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
  ) {
    super(`request failed (${status}): ${body}`);
  }
}

export async function getConfig(): Promise<OspreyConfig> {
  return asJson(await fetch("/api/config"));
}

export async function putConfig(patch: Partial<OspreyConfig>): Promise<OspreyConfig> {
  return asJson(
    await fetch("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  );
}

export async function getProfileOptions(profile: string): Promise<ProfileOptions> {
  return asJson(await fetch(`/api/profile-options/${profile}`));
}

export async function postConsequences(config: OspreyConfig): Promise<Consequences> {
  return asJson(
    await fetch("/api/consequences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  );
}
