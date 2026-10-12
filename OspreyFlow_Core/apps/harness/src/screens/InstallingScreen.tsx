import { useEffect, useRef, useState } from "react";

import { streamInstall } from "../api/client";

export function InstallingScreen() {
  const [lines, setLines] = useState<string[]>([]);
  const [returncode, setReturncode] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    streamInstall(
      (line) => setLines((now) => [...now, line]),
      (code) => setReturncode(code),
      (message) => setError(message),
    );
  }, []);

  const finished = returncode !== null || error !== null;

  return (
    <section aria-labelledby="installing-heading">
      <h2 id="installing-heading">Installing</h2>
      {!finished && <p>The install is running. This can take a while; leave this page open.</p>}
      <pre role="log" aria-label="Install output" aria-live="polite">
        {lines.map((line, index) => (
          <span key={index}>
            {line}
            {"\n"}
          </span>
        ))}
      </pre>
      {error && <p role="alert">{error}</p>}
      {returncode === 0 && (
        <p role="status">OspreyFlow is installed. The address and where the sign-in details are kept are printed above.</p>
      )}
      {returncode !== null && returncode !== 0 && (
        <p role="alert">
          The install failed (exit {returncode}). Its output is above; fix what it names and run
          ospreyflow install again.
        </p>
      )}
      {finished && <p>This page closes now.</p>}
    </section>
  );
}
