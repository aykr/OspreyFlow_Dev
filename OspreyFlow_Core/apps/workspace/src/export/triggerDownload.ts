// Phase 8 Stage 4h: the one download mechanism shared by all three artefact shapes — a plain
// anchor-click against an object URL, no new dependency. `URL.revokeObjectURL` is deferred to the
// next tick (not called synchronously) since some browsers cancel the download if the URL is
// revoked before the click has been dispatched.
export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
