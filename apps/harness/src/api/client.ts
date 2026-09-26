// `05_DEPLOYMENT.md` §2.3: "the UI never has a capability the headless path lacks." Every call
// here reaches exactly one of `harness/webapp.py`'s own routes — no client-side logic invents a
// capability the Python layer does not already expose. See that module's own docstring for the
// full UI→headless map this round's report cites.
import type {
  ArtefactsResult,
  Consequences,
  MapConfig,
  NewRealDataException,
  OspreyConfig,
  PreflightCheckResult,
  ProfileOptions,
  RealDataException,
} from "./types";

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

export async function getRealDataExceptions(): Promise<{ exceptions: RealDataException[] }> {
  return asJson(await fetch("/api/real-data-exceptions"));
}

export async function addRealDataException(
  entry: NewRealDataException,
): Promise<RealDataException> {
  return asJson(
    await fetch("/api/real-data-exceptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entry),
    }),
  );
}

export async function removeRealDataException(dataset: string): Promise<void> {
  const response = await fetch(`/api/real-data-exceptions/${encodeURIComponent(dataset)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
}

export async function registerLocalProvider(body: {
  provider_id: string;
  label: string;
  pmtiles_path: string;
}): Promise<MapConfig> {
  return asJson(
    await fetch("/api/geospatial/register-provider", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function buildLocalBasemap(): Promise<void> {
  const response = await fetch("/api/geospatial/build-basemap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
}

export async function verifyMap(): Promise<void> {
  const response = await fetch("/api/geospatial/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
}

// `harness/preflight/__main__.py`'s own `run_streaming` — one `EventSource` per stream, since a
// native browser `EventSource` is exactly "each check appears as it completes"
// (`05_DEPLOYMENT.md` §2.1) with nothing invented on top. The caller closes the returned
// `EventSource` itself if it needs to abandon a stream early; a normal run closes itself on the
// server's own `complete` event.
export function streamPreflight(
  onResult: (result: PreflightCheckResult) => void,
  onComplete: () => void,
  options?: { only?: string; seeding?: boolean },
): EventSource {
  const params = new URLSearchParams();
  if (options?.only) params.set("only", options.only);
  if (options?.seeding) params.set("seeding", "true");
  const query = params.toString();
  const source = new EventSource(`/api/preflight/stream${query ? `?${query}` : ""}`);
  source.onmessage = (event) => {
    onResult(JSON.parse(event.data as string) as PreflightCheckResult);
  };
  source.addEventListener("complete", () => {
    source.close();
    onComplete();
  });
  return source;
}

export async function generateArtefacts(): Promise<ArtefactsResult> {
  return asJson(await fetch("/api/artefacts/generate", { method: "POST" }));
}

export async function getArtefacts(): Promise<{
  artefacts: Record<string, string>;
  confirmed: boolean;
}> {
  return asJson(await fetch("/api/artefacts"));
}

export async function confirmArtefacts(): Promise<{ confirmed: boolean }> {
  return asJson(await fetch("/api/artefacts/confirm", { method: "POST" }));
}

export function artefactDownloadUrl(name: string): string {
  return `/api/artefacts/${encodeURIComponent(name)}`;
}
