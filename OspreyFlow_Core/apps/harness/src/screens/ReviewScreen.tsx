import { useEffect, useState } from "react";

import { errorMessage, getInstallDoctor } from "../api/client";
import type { DoctorResult, InstallAnswers, InstallState, OspreyConfig } from "../api/types";

const MODE_WORDS = { lite: "Lite", small: "Small", enterprise: "Enterprise" } as const;

export function ReviewScreen({
  state,
  config,
  onInstall,
  onSaveAnswers,
}: {
  state: InstallState;
  config: OspreyConfig;
  onInstall: () => void;
  onSaveAnswers: (answers: InstallAnswers) => Promise<void>;
}) {
  const [doctor, setDoctor] = useState<DoctorResult | null>(null);
  const [doctorError, setDoctorError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const mode = state.mode;
  const answers = state.answers;
  const says = state.modes[mode].says;

  useEffect(() => {
    let cancelled = false;
    getInstallDoctor()
      .then((result) => {
        if (!cancelled) setDoctor(result);
      })
      .catch((exc) => {
        if (!cancelled) setDoctorError(errorMessage(exc));
      });
    return () => {
      cancelled = true;
    };
  }, [mode]);

  async function handleSaveAnswers() {
    setError(null);
    try {
      await onSaveAnswers({ ...answers, mode });
      setSaved(true);
    } catch (exc) {
      setError(errorMessage(exc));
    }
  }

  const titles = state.packs
    .filter((p) => answers.demo_packs?.includes(p.id))
    .map((p) => p.title);
  const storage = config.components?.storage;
  const cloud = answers.cloud;

  return (
    <section aria-labelledby="review-heading">
      <h2 id="review-heading">Review</h2>
      <ul aria-label="Your answers">
        <li>Mode: {MODE_WORDS[mode]}</li>
        {mode === "lite" ? (
          <>
            <li>Ingest folder: {storage?.ingest ?? "not chosen"}</li>
            <li>Basemap folder: {storage?.tiles ?? "not chosen"}</li>
          </>
        ) : (
          <>
            <li>Cloud: {cloud?.provider ?? "not chosen"}</li>
            <li>Region: {cloud?.region || "not chosen"}</li>
            <li>Size: {cloud?.size ?? "not chosen"}</li>
            <li>Domain: {cloud?.domain || "not chosen"}</li>
          </>
        )}
        <li>Demo packs: {titles.length ? titles.join(", ") : "none"}</li>
      </ul>

      <h3 id="doctor-heading">Your computer</h3>
      {!doctor && !doctorError && <p>Checking…</p>}
      {doctorError && <p role="alert">{doctorError}</p>}
      {doctor && (
        <>
          <pre role="log" aria-labelledby="doctor-heading">
            {doctor.lines.map((line, index) => (
              <span key={index}>
                {line}
                {"\n"}
              </span>
            ))}
          </pre>
          <p>
            {doctor.returncode === 0
              ? "Every check passed."
              : "Some checks did not pass. Fix what is listed above; the install stops at the same checks."}
          </p>
        </>
      )}

      {error && <p role="alert">{error}</p>}
      {mode === "lite" ? (
        <button type="button" className="btn btn--primary" onClick={onInstall}>
          Install
        </button>
      ) : (
        <>
          <p>{says}</p>
          <button type="button" className="btn btn--primary" onClick={handleSaveAnswers}>
            Save answers
          </button>
          {saved && <p role="status">Your answers are saved.</p>}
        </>
      )}
    </section>
  );
}
