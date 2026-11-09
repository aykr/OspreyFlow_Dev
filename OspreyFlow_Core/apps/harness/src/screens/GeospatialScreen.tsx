import { useState } from "react";

import { ApiError, buildLocalBasemap, registerLocalProvider, verifyMap, type MapStepResult } from "../api/client";

/** What a Build or Verify said: the Conduit's own lines, or its refusal in words. */
function said(result: MapStepResult, done: string, failed: string): string {
  const head = result.returncode === 0 ? done : failed;
  return [head, ...result.lines].join("\n");
}

export function GeospatialScreen() {
  const [providerId, setProviderId] = useState("");
  const [label, setLabel] = useState("");
  const [pmtilesPath, setPmtilesPath] = useState("");
  const [registerResult, setRegisterResult] = useState<string | null>(null);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [region, setRegion] = useState("rutland");
  const [unit, setUnit] = useState("");
  const [buildResult, setBuildResult] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleRegister() {
    setSaving(true);
    setRegisterError(null);
    setRegisterResult(null);
    try {
      const result = await registerLocalProvider({
        provider_id: providerId,
        label,
        pmtiles_path: pmtilesPath,
      });
      setRegisterResult(`Registered — default provider is now ${result.default}.`);
    } catch (exc) {
      setRegisterError(exc instanceof ApiError ? exc.body : String(exc));
    } finally {
      setSaving(false);
    }
  }

  async function handleBuild() {
    setBuildResult("Building… this can take many minutes for a large region.");
    try {
      setBuildResult(said(await buildLocalBasemap(region, unit), "Built.", "The build did not finish."));
    } catch (exc) {
      setBuildResult(exc instanceof ApiError ? exc.body : String(exc));
    }
  }

  async function handleVerify() {
    setVerifyResult(null);
    try {
      setVerifyResult(said(await verifyMap(), "Verify passed.", "Verify found issues."));
    } catch (exc) {
      setVerifyResult(exc instanceof ApiError ? exc.body : String(exc));
    }
  }

  return (
    <section aria-labelledby="geospatial-heading">
      <h2 id="geospatial-heading">Geospatial</h2>

      <h3>Register a local (tier-1) provider</h3>
      <label htmlFor="geo-provider-id">Provider id</label>
      <input
        id="geo-provider-id"
        className="input"
        value={providerId}
        onChange={(event) => setProviderId(event.target.value)}
      />
      <label htmlFor="geo-label">Label</label>
      <input
        id="geo-label"
        className="input"
        value={label}
        onChange={(event) => setLabel(event.target.value)}
      />
      <label htmlFor="geo-pmtiles-path">PMTiles path</label>
      <input
        id="geo-pmtiles-path"
        className="input"
        value={pmtilesPath}
        onChange={(event) => setPmtilesPath(event.target.value)}
      />
      {registerError && <p role="alert">{registerError}</p>}
      {registerResult && <p role="status">{registerResult}</p>}
      <button
        type="button"
        className="btn btn--primary"
        onClick={handleRegister}
        disabled={saving}
      >
        Register provider
      </button>

      <h3>Build local basemap</h3>
      <p>
        Built by the Conduit once the deployment is launched: it downloads the region&apos;s
        Geofabrik extract, runs planetiler and loads the place names (<code>05_DEPLOYMENT.md</code>{" "}
        §2.2). Rutland is small enough to build in minutes. The same as{" "}
        <code>ospreyflow map build</code>.
      </p>
      <label htmlFor="geo-region">Region</label>
      <input
        id="geo-region"
        className="input"
        value={region}
        onChange={(event) => setRegion(event.target.value)}
      />
      <label htmlFor="geo-unit">Unit that holds the place names</label>
      <p id="geo-unit-help">
        The unit whose cases may add this region&apos;s places: one that already holds a case or a
        dataset here. The same as <code>ospreyflow map build --unit</code>.
      </p>
      <input
        id="geo-unit"
        className="input"
        aria-describedby="geo-unit-help"
        value={unit}
        onChange={(event) => setUnit(event.target.value)}
      />
      {buildResult && (
        <p role="status" style={{ whiteSpace: "pre-line" }}>
          {buildResult}
        </p>
      )}
      <button type="button" className="btn" onClick={handleBuild}>
        Build local basemap
      </button>

      <h3>Verify</h3>
      <p>Checks attribution and, for a tier-4 provider, CRS/zoom. The same as <code>ospreyflow map verify</code>.</p>
      {verifyResult && (
        <p role="status" style={{ whiteSpace: "pre-line" }}>
          {verifyResult}
        </p>
      )}
      <button type="button" className="btn" onClick={handleVerify}>
        Verify
      </button>
    </section>
  );
}
