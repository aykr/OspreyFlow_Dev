// Fetch wrappers for `/v1/investigations/{id}/sites/*` (`services/api/app.py`)
// — mirrors `map/providers.ts`'s `fetchMapConfig` convention exactly. `Site`
// is hand-typed here rather than generated: it is Conduit-local control-plane
// metadata (`services/api/sites.py`), the same category as `Investigation`,
// which the frontend also does not generate a type for.
import type { ControlPoint } from "./bilinear";

export interface SiteControlPoint {
  px: number;
  py: number;
  lon: number;
  lat: number;
}

export interface Site {
  id: string;
  investigation_id: string;
  owning_unit: string;
  created_at: string;
  created_by: string;
  label: string;
  image_object_key: string;
  image_width_px: number;
  image_height_px: number;
  control_points:
    | readonly [
        SiteControlPoint,
        SiteControlPoint,
        SiteControlPoint,
        SiteControlPoint,
      ]
    | null;
  grid_rows: number | null;
  grid_cols: number | null;
}

function authHeaders(bearerToken: string): HeadersInit {
  return { Authorization: `Bearer ${bearerToken}` };
}

async function parseOrThrow(response: Response, action: string): Promise<Site> {
  if (!response.ok) {
    throw new Error(`${action} failed: ${response.status}`);
  }
  return (await response.json()) as Site;
}

export async function createSite(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  label: string,
  image: File,
): Promise<Site> {
  const form = new FormData();
  form.append("label", label);
  form.append("image", image);
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/sites`,
    {
      method: "POST",
      headers: authHeaders(bearerToken),
      body: form,
    },
  );
  return parseOrThrow(response, "POST .../sites");
}

export async function setSiteControlPoints(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  siteId: string,
  // TL, TR, BR, BL — same winding order `bilinear.ts` assumes throughout.
  controlPoints: readonly [
    ControlPoint,
    ControlPoint,
    ControlPoint,
    ControlPoint,
  ],
): Promise<Site> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/sites/${siteId}/control-points`,
    {
      method: "PATCH",
      headers: {
        ...authHeaders(bearerToken),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ control_points: controlPoints }),
    },
  );
  return parseOrThrow(response, "PATCH .../control-points");
}

export async function setSiteGrid(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  siteId: string,
  rows: number,
  cols: number,
): Promise<Site> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/sites/${siteId}/grid`,
    {
      method: "POST",
      headers: {
        ...authHeaders(bearerToken),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ rows, cols }),
    },
  );
  return parseOrThrow(response, "POST .../grid");
}

export async function getSite(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  siteId: string,
): Promise<Site> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/sites/${siteId}`,
    { headers: authHeaders(bearerToken) },
  );
  return parseOrThrow(response, "GET .../sites/{id}");
}

/** Not a plain `<img src>` url the browser can fetch unauthenticated — the
 * route requires a bearer token (`services/api/site_images.py`'s own
 * "the browser never talks to the object store directly" reasoning
 * extends to this proxy route too). Callers that render this in MapLibre
 * attach the token via `transformRequest` (`MapView.tsx`) rather than a
 * query-string token, consistent with how the delta-stream websocket is
 * the one documented exception to that rule, not a second one. */
export function siteImageUrl(
  apiBaseUrl: string,
  investigationId: string,
  siteId: string,
): string {
  return `${apiBaseUrl}/v1/investigations/${investigationId}/sites/${siteId}/image`;
}

/** For a plain `<img>` element (`SiteCalibrationWizard.tsx`'s calibration
 * step), which — unlike MapLibre's `image` source — has no
 * `transformRequest`-style hook to attach a header to its own fetch.
 * Fetches the bytes with the bearer token and hands back a `blob:` object
 * URL the `<img>` can use instead; the caller owns revoking it
 * (`URL.revokeObjectURL`) once it's no longer displayed. */
export async function fetchSiteImageObjectUrl(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  siteId: string,
): Promise<string> {
  const response = await fetch(siteImageUrl(apiBaseUrl, investigationId, siteId), {
    headers: authHeaders(bearerToken),
  });
  if (!response.ok) {
    throw new Error(`GET .../image failed: ${response.status}`);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}
