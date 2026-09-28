// The site geospatial UI — `spec/02_GLASS_FRONTEND.md` §3.5 ("Support an
// uploaded image with two or more control points and a drawn grid, and let
// a `Location` entity be a grid cell"), `08_ACCEPTANCE_SCENARIOS.md` A1.
//
// **A per-investigation analyst artifact, not a `MapProvider` registry
// entry.** `spec/00_ARCHITECTURE.md` §1.2's `kind: image` provider
// (`osprey.yaml`'s `site-4471` example) is a *different*, ops-provisioned
// case: a pre-georeferenced GeoTIFF a deployment drops into config ahead
// of time. This wizard is what *produces* a georeferencing from a plain
// uploaded photo, by the analyst placing control points live — that
// mechanism has no equivalent in the provider registry, and this
// checkpoint does not add one; see `services/api/sites.py`'s own
// docstring for the same distinction stated server-side.
//
// **A bounded, one-directional flow** — upload, four paired clicks, a
// grid size, confirm — not a general editor: no drag-to-reposition a
// point, no undo, no re-ordering. Proportionate to this checkpoint;
// redoing a miscalibrated site today means starting a new one.
import { useEffect, useState } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";

import { Button } from "../design/primitives/Button";
import {
  createSite,
  fetchSiteImageObjectUrl,
  setSiteControlPoints,
  setSiteGrid,
  siteImageUrl,
  type Site,
} from "./api";
import type { ControlPoint } from "./bilinear";
import { computeGridCells, formsASimpleQuadrilateral } from "./bilinear";
import {
  onNextMapClick,
  removeAllSiteLayers,
  setSiteGridLayer,
  setSiteImageLayer,
} from "./siteLayer";

const CORNER_LABELS = [
  "top-left",
  "top-right",
  "bottom-right",
  "bottom-left",
] as const;

type Step =
  | { kind: "upload" }
  | {
      kind: "click-image";
      site: Site;
      cornerIndex: number;
      imagePoints: { px: number; py: number }[];
    }
  | {
      kind: "click-map";
      site: Site;
      cornerIndex: number;
      imagePoints: { px: number; py: number }[];
      mapPoints: { lon: number; lat: number }[];
    }
  | { kind: "grid"; site: Site; rows: number; cols: number }
  | { kind: "confirmed"; site: Site };

export interface SiteCalibrationWizardProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** `null` while the Map view isn't mounted — the "click the matching
   * point on the map" step needs a live `maplibregl.Map`
   * (`MapView.tsx`'s `onMapReady`), and has nothing to attach a listener
   * to without one. */
  map: MapLibreMap | null;
  onClose: () => void;
}

export function SiteCalibrationWizard({
  apiBaseUrl,
  bearerToken,
  investigationId,
  map,
  onClose,
}: SiteCalibrationWizardProps) {
  const [step, setStep] = useState<Step>({ kind: "upload" });
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imageObjectUrl, setImageObjectUrl] = useState<string | null>(null);

  // A plain `<img>` has no `transformRequest`-style hook (unlike
  // MapLibre's `image` source, wired in `finishControlPoints` below) — the
  // image proxy route requires a bearer token, so the calibration step
  // fetches the bytes itself and displays a `blob:` object URL instead of
  // pointing `src` at the authenticated route directly. Revoked on
  // cleanup so a re-render or step change doesn't leak object URLs.
  const imageSiteId = step.kind === "click-image" ? step.site.id : null;
  useEffect(() => {
    if (imageSiteId === null) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    void fetchSiteImageObjectUrl(apiBaseUrl, bearerToken, investigationId, imageSiteId).then(
      (url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setImageObjectUrl(url);
      },
    );
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [imageSiteId, apiBaseUrl, bearerToken, investigationId]);

  async function handleUpload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const site = await createSite(
        apiBaseUrl,
        bearerToken,
        investigationId,
        label || file.name,
        file,
      );
      setStep({ kind: "click-image", site, cornerIndex: 0, imagePoints: [] });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function handleImageClick(
    event: React.MouseEvent<HTMLImageElement>,
    current: Extract<Step, { kind: "click-image" }>,
  ) {
    const img = event.currentTarget;
    const rect = img.getBoundingClientRect();
    const scaleX = current.site.image_width_px / rect.width;
    const scaleY = current.site.image_height_px / rect.height;
    const px = (event.clientX - rect.left) * scaleX;
    const py = (event.clientY - rect.top) * scaleY;
    const imagePoints = [...current.imagePoints, { px, py }];

    if (imagePoints.length < 4) {
      setStep({
        ...current,
        cornerIndex: current.cornerIndex + 1,
        imagePoints,
      });
    } else {
      setStep({
        kind: "click-map",
        site: current.site,
        cornerIndex: 0,
        imagePoints,
        mapPoints: [],
      });
    }
  }

  function armNextMapClick(current: Extract<Step, { kind: "click-map" }>) {
    if (!map) return;
    setError(null);
    onNextMapClick(map, ({ lng, lat }) => {
      const mapPoints = [...current.mapPoints, { lon: lng, lat }];
      if (mapPoints.length < 4) {
        setStep({
          ...current,
          cornerIndex: current.cornerIndex + 1,
          mapPoints,
        });
      } else {
        void finishControlPoints(current.site, current.imagePoints, mapPoints);
      }
    });
  }

  async function finishControlPoints(
    site: Site,
    imagePoints: { px: number; py: number }[],
    mapPoints: { lon: number; lat: number }[],
  ) {
    // Checked before anything is persisted, on the world (map) points —
    // those are what actually determine the quad's shape; `computeGridCells`
    // never reads `px`/`py` at all. Catches a scrambled click order (e.g.
    // the BR/BL clicks swapped) that would otherwise silently produce a
    // crossed, badly warped grid rather than an error — see
    // `bilinear.ts`'s `formsASimpleQuadrilateral` docstring.
    if (!formsASimpleQuadrilateral(mapPoints)) {
      setError(
        "Those four map points don't form a simple top-left → top-right → " +
          "bottom-right → bottom-left quadrilateral (two corners look swapped). " +
          "Click the four map points again, in that order.",
      );
      setStep({ kind: "click-map", site, cornerIndex: 0, imagePoints, mapPoints: [] });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Both arrays are guaranteed length 4 here — this is only called
      // once `click-map`'s own state machine has collected a fourth point
      // (see the call site in `armNextMapClick`).
      const controlPoints = imagePoints.map((p, i) => ({
        px: p.px,
        py: p.py,
        lon: mapPoints[i]!.lon,
        lat: mapPoints[i]!.lat,
      })) as [ControlPoint, ControlPoint, ControlPoint, ControlPoint];
      const updated = await setSiteControlPoints(
        apiBaseUrl,
        bearerToken,
        investigationId,
        site.id,
        controlPoints,
      );
      if (map && updated.control_points) {
        setSiteImageLayer(
          map,
          siteImageUrl(apiBaseUrl, investigationId, site.id),
          updated.control_points as [
            ControlPoint,
            ControlPoint,
            ControlPoint,
            ControlPoint,
          ],
        );
        previewGrid(map, updated, 10, 10);
      }
      setStep({ kind: "grid", site: updated, rows: 10, cols: 10 });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function previewGrid(m: MapLibreMap, site: Site, rows: number, cols: number) {
    if (!site.control_points) return;
    const cells = computeGridCells(
      site.control_points as [
        ControlPoint,
        ControlPoint,
        ControlPoint,
        ControlPoint,
      ],
      rows,
      cols,
    );
    setSiteGridLayer(m, cells);
  }

  function handleGridDimensionChange(
    current: Extract<Step, { kind: "grid" }>,
    rows: number,
    cols: number,
  ) {
    setStep({ ...current, rows, cols });
    if (map) previewGrid(map, current.site, rows, cols);
  }

  async function handleConfirmGrid(current: Extract<Step, { kind: "grid" }>) {
    setBusy(true);
    setError(null);
    try {
      const confirmed = await setSiteGrid(
        apiBaseUrl,
        bearerToken,
        investigationId,
        current.site.id,
        current.rows,
        current.cols,
      );
      setStep({ kind: "confirmed", site: confirmed });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function handleClose() {
    if (map) removeAllSiteLayers(map);
    onClose();
  }

  return (
    <div
      style={{
        position: "absolute",
        top: 8,
        left: 8,
        width: 320,
        background: "var(--surface-raised)",
        border: "1px solid var(--border-subtle)",
        borderRadius: 4,
        padding: "var(--sp-16)",
        color: "var(--text-primary)",
        zIndex: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <strong>Site geospatial</strong>
        <Button onClick={handleClose}>Close</Button>
      </div>

      {error && <p style={{ color: "var(--status-danger)" }}>{error}</p>}

      {step.kind === "upload" && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-8)",
          }}
        >
          <p>Upload a site image (aerial photo or plan) to calibrate.</p>
          <input
            type="text"
            placeholder="Label (e.g. HMP Hollywood aerial)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <input
            type="file"
            accept="image/png,image/jpeg"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleUpload(file);
            }}
          />
        </div>
      )}

      {step.kind === "click-image" && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-8)",
          }}
        >
          <p>
            Click the <strong>{CORNER_LABELS[step.cornerIndex]}</strong> corner
            on the image ({step.imagePoints.length}/4 placed).
          </p>
          {imageObjectUrl ? (
            <img
              src={imageObjectUrl}
              alt={step.site.label}
              style={{ maxWidth: "100%", cursor: "crosshair" }}
              onClick={(e) => handleImageClick(e, step)}
            />
          ) : (
            <p>Loading image…</p>
          )}
        </div>
      )}

      {step.kind === "click-map" && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-8)",
          }}
        >
          <p>
            Now click the matching{" "}
            <strong>{CORNER_LABELS[step.cornerIndex]}</strong> location on the
            map ({step.mapPoints.length}/4 placed).
          </p>
          {!map && <p>Switch to the Map view to continue.</p>}
          {map && step.mapPoints.length === step.cornerIndex && (
            <Button onClick={() => armNextMapClick(step)}>
              Ready — click the map
            </Button>
          )}
        </div>
      )}

      {step.kind === "grid" && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--sp-8)",
          }}
        >
          <p>
            Draw the grid (`08_ACCEPTANCE_SCENARIOS.md` A1's default is 10x10).
          </p>
          <label>
            Rows
            <input
              type="number"
              min={1}
              value={step.rows}
              onChange={(e) =>
                handleGridDimensionChange(
                  step,
                  Number(e.target.value) || 1,
                  step.cols,
                )
              }
            />
          </label>
          <label>
            Columns
            <input
              type="number"
              min={1}
              value={step.cols}
              onChange={(e) =>
                handleGridDimensionChange(
                  step,
                  step.rows,
                  Number(e.target.value) || 1,
                )
              }
            />
          </label>
          <Button onClick={() => void handleConfirmGrid(step)}>
            {busy ? "Creating grid cells…" : "Confirm grid"}
          </Button>
        </div>
      )}

      {step.kind === "confirmed" && (
        <div>
          <p>
            Grid confirmed: {step.site.grid_rows}×{step.site.grid_cols} cells
            created as <code>Location</code> entities.
          </p>
        </div>
      )}
    </div>
  );
}
