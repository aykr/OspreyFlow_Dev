import { useEffect, useState } from "react";

import { ApiError, postConsequences } from "../api/client";
import type { Consequences, OspreyConfig, Profile } from "../api/types";

const PROFILES: { value: Profile; label: string }[] = [
  { value: "local-lite", label: "local-lite — one laptop" },
  { value: "small", label: "small — a few machines" },
  { value: "cluster", label: "cluster — ten or more machines" },
];

export function ProfileScreen({
  config,
  onSave,
}: {
  config: OspreyConfig;
  onSave: (patch: Partial<OspreyConfig>) => Promise<void>;
}) {
  const [selected, setSelected] = useState<Profile>(config.profile ?? "local-lite");
  // S11 (the owner's ruling of 2 November 2026): Small and Enterprise are HTTPS, so choosing one
  // asks for its address, saved with the profile in one write; Lite keeps its own address.
  const savedOrigin = config.network?.public_origin ?? "";
  const [address, setAddress] = useState(savedOrigin.startsWith("https://") ? savedOrigin : "");
  const cloud = selected !== "local-lite";
  const [consequences, setConsequences] = useState<Consequences | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSelected(config.profile ?? "local-lite");
  }, [config.profile]);

  useEffect(() => {
    // §2.1: "consequences are shown, not described... updating as later screens change" — a live
    // preview against the draft selection, before Save is ever pressed.
    let cancelled = false;
    postConsequences({ ...config, profile: selected })
      .then((result) => {
        if (!cancelled) setConsequences(result);
      })
      .catch(() => {
        if (!cancelled) setConsequences(null);
      });
    return () => {
      cancelled = true;
    };
  }, [config, selected]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave(
        cloud ? { profile: selected, network: { ...config.network, public_origin: address.trim() } } : { profile: selected },
      );
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.body : String(exc));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="profile-heading">
      <h2 id="profile-heading">Profile</h2>
      <fieldset>
        <legend>Choose a profile</legend>
        {PROFILES.map(({ value, label }) => (
          <label key={value} style={{ display: "block" }}>
            <input
              type="radio"
              name="profile"
              value={value}
              checked={selected === value}
              onChange={() => setSelected(value)}
            />{" "}
            {label}
          </label>
        ))}
      </fieldset>

      {cloud && (
        <>
          <label htmlFor="profile-address">Address (https://…)</label>
          <input
            id="profile-address"
            type="url"
            inputMode="url"
            required
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            aria-describedby="profile-address-help"
            placeholder="https://osprey.example.org"
          />
          <p id="profile-address-help" className="help">
            {selected === "small" ? "A Small" : "An Enterprise"} deployment is reached by other people over a network, so
            its address is HTTPS: the front proxy obtains its certificate. Plain HTTP is for Lite, on this computer only.
          </p>
        </>
      )}

      {consequences && (
        <dl aria-label="Consequences of this choice">
          <dt>Machines</dt>
          <dd>{consequences.machines}</dd>
          <dt>Orchestrator</dt>
          <dd>{consequences.orchestrator}</dd>
          <dt>Memory floor</dt>
          <dd>{consequences.memory_gb_floor} GB</dd>
        </dl>
      )}

      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
        Save profile
      </button>
    </section>
  );
}
