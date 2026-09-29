import { useState } from "react";

import { ApiError, buildLocalBasemap, registerLocalProvider, verifyMap } from "../api/client";

export function GeospatialScreen() {
  const [providerId, setProviderId] = useState("");
  const [label, setLabel] = useState("");
  const [pmtilesPath, setPmtilesPath] = useState("");
  const [registerResult, setRegisterResult] = useState<string | null>(null);
  const [registerError, setRegisterError] = useState<string | null>(null);
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
    setBuildResult(null);
    try {
      await buildLocalBasemap();
      setBuildResult("Build local basemap succeeded.");
    } catch (exc) {
      setBuildResult(exc instanceof ApiError ? exc.body : String(exc));
    }
  }

  async function handleVerify() {
    setVerifyResult(null);
    try {
      await verifyMap();
      setVerifyResult("Verify succeeded.");
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
        Downloads a Geofabrik extract, runs planetiler, loads the OSM-derived gazetteer
        (<code>05_DEPLOYMENT.md</code> §2.2). Not available from this setup harness this round —
        see the result below for the real reason.
      </p>
      {buildResult && <p role="status">{buildResult}</p>}
      <button type="button" className="btn" onClick={handleBuild}>
        Build local basemap
      </button>

      <h3>Verify</h3>
      <p>Checks attribution and, for a tier-4 provider, CRS/zoom.</p>
      {verifyResult && <p role="status">{verifyResult}</p>}
      <button type="button" className="btn" onClick={handleVerify}>
        Verify
      </button>
    </section>
  );
}
