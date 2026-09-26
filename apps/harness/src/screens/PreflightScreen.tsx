import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  artefactDownloadUrl,
  confirmArtefacts,
  confirmLaunchTarget,
  generateArtefacts,
  getArtefacts,
  getLaunchTarget,
  streamLaunch,
  streamPreflight,
} from "../api/client";
import type { ArtefactsResult, LaunchTarget, PreflightCheckResult } from "../api/types";

const ARTEFACT_NAMES = ["compose.yaml", "deployment.env", "versions.lock", "RUNBOOK.md"] as const;

//: `harness.preflight.ALL_CHECKS`'s own order — kept identical so a check the stream has not yet
//: reported for shows as its own row rather than appearing only once results arrive.
const CHECK_NAMES = [
  "memory",
  "disk",
  "gpu",
  "ports",
  "container-runtime",
  "cluster-connectivity",
  "interpreter",
  "bind-address",
  "basemap",
  "duckdb-lock",
  "oidc-audience",
] as const;

function ArtefactsSection({
  artefacts,
  confirmed,
  onGenerated,
  onConfirmed,
}: {
  artefacts: ArtefactsResult | { artefacts: Record<string, string>; confirmed: boolean } | null;
  confirmed: boolean;
  onGenerated: (result: ArtefactsResult) => void;
  onConfirmed: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      onGenerated(await generateArtefacts());
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.body : String(exc));
    } finally {
      setGenerating(false);
    }
  }

  async function handleConfirm() {
    try {
      await confirmArtefacts();
      onConfirmed();
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.body : String(exc));
    }
  }

  const diffs = artefacts && "diffs" in artefacts ? artefacts.diffs : undefined;

  return (
    <section aria-labelledby="artefacts-heading">
      <h3 id="artefacts-heading">Generated artefacts</h3>
      <p>
        Shown before anything runs (<code>05_DEPLOYMENT.md</code> §2.1/§2.4) — <code>osprey.yaml</code>{" "}
        is the source; these four are produced from it by <code>harness/render.py</code> and
        written to <code>deploy/generated/&lt;profile&gt;/</code>.
      </p>

      {error && <p role="alert">{error}</p>}
      <button
        type="button"
        className="btn btn--primary"
        onClick={handleGenerate}
        disabled={generating}
      >
        Generate
      </button>

      {artefacts && (
        <>
          <ul>
            {ARTEFACT_NAMES.map((name) => (
              <li key={name}>
                {name}
                {diffs && diffs[name] && <span> — changed</span>}
                {diffs && !diffs[name] && <span> — unchanged</span>}{" "}
                <a href={artefactDownloadUrl(name)} download={name}>
                  Download {name}
                </a>
              </li>
            ))}
          </ul>

          <button type="button" className="btn" onClick={handleConfirm} disabled={confirmed}>
            {confirmed ? "Artefacts confirmed" : "Confirm artefacts"}
          </button>
        </>
      )}
    </section>
  );
}

function LaunchSection({ enabled }: { enabled: boolean }) {
  const [target, setTarget] = useState<LaunchTarget | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const [launching, setLaunching] = useState(false);
  const [returncode, setReturncode] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    getLaunchTarget()
      .then(setTarget)
      .catch(() => {
        // No docker context resolvable yet — a real, if unusual, first-load state.
      });
    return () => controllerRef.current?.abort();
  }, []);

  async function handleConfirmTarget() {
    try {
      setTarget(await confirmLaunchTarget());
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.body : String(exc));
    }
  }

  function handleLaunch() {
    setLaunching(true);
    setLines([]);
    setReturncode(null);
    setError(null);
    controllerRef.current = streamLaunch(
      (line) => setLines((previous) => [...previous, line]),
      (code) => {
        setReturncode(code);
        setLaunching(false);
      },
      (message) => {
        setError(message);
        setLaunching(false);
      },
    );
  }

  const launchDisabled = !enabled || !target?.confirmed || launching;

  return (
    <section aria-labelledby="launch-heading">
      <h3 id="launch-heading">Launch</h3>
      {target && (
        <p>
          Docker target: <strong>{target.docker_context}</strong>
          {target.confirmed ? " (confirmed)" : " (not yet confirmed)"}
        </p>
      )}
      <button
        type="button"
        className="btn"
        onClick={handleConfirmTarget}
        disabled={target?.confirmed}
      >
        Confirm target
      </button>

      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleLaunch} disabled={launchDisabled}>
        Launch
      </button>

      {lines.length > 0 && (
        <pre role="log" aria-label="Launch output">
          {lines.join("\n")}
        </pre>
      )}
      {returncode !== null && (
        <p role="status">
          {returncode === 0 ? "Launch succeeded." : `Launch failed (exit ${returncode}).`}
        </p>
      )}
    </section>
  );
}

export function PreflightScreen() {
  const [artefacts, setArtefacts] = useState<ArtefactsResult | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [results, setResults] = useState<Record<string, PreflightCheckResult>>({});
  const [running, setRunning] = useState(false);
  const [rechecking, setRechecking] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    getArtefacts()
      .then((result) => {
        setConfirmed(result.confirmed);
      })
      .catch(() => {
        // Nothing generated yet this session — the real, expected first-load state.
      });
    return () => {
      sourceRef.current?.close();
    };
  }, []);

  function handleGenerated(result: ArtefactsResult) {
    setArtefacts(result);
    setConfirmed(false);
  }

  function runPreflight(only?: string) {
    if (only) setRechecking(only);
    else {
      setRunning(true);
      setResults({});
    }
    sourceRef.current?.close();
    sourceRef.current = streamPreflight(
      (result) => {
        setResults((previous) => ({ ...previous, [result.check]: result }));
      },
      () => {
        setRunning(false);
        setRechecking(null);
      },
      { only },
    );
  }

  const allReported = CHECK_NAMES.every((name) => results[name] !== undefined);
  const anyFailing = Object.values(results).some((r) => r.status === "fail");
  const launchDisabled = !allReported || anyFailing;

  return (
    <section aria-labelledby="preflight-heading">
      <h2 id="preflight-heading">Preflight</h2>

      <ArtefactsSection
        artefacts={artefacts}
        confirmed={confirmed}
        onGenerated={handleGenerated}
        onConfirmed={() => setConfirmed(true)}
      />

      <h3>Checks</h3>
      <button
        type="button"
        className="btn btn--primary"
        onClick={() => runPreflight()}
        disabled={running || rechecking !== null}
      >
        Run preflight
      </button>

      <ul>
        {CHECK_NAMES.map((name) => {
          const result = results[name];
          return (
            <li key={name}>
              <strong>{name}</strong>
              {result ? (
                <>
                  {" "}
                  — {result.status}
                  {result.status !== "pass" && <span> — {result.what_is_wrong}</span>}
                  {result.detail.length > 0 && (
                    <ul>
                      {result.detail.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  )}
                </>
              ) : (
                <span> — not yet run</span>
              )}{" "}
              <button
                type="button"
                className="btn"
                onClick={() => runPreflight(name)}
                disabled={running || rechecking !== null}
              >
                Re-check {name}
              </button>
            </li>
          );
        })}
      </ul>

      {anyFailing && (
        <p role="status">
          Launch is disabled while a check is failing. A warning or a skipped check does not block
          it.
        </p>
      )}

      <LaunchSection enabled={!launchDisabled && confirmed} />
    </section>
  );
}
