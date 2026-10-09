// A listed file's size, said so it never claims what is not so (spec 09 §3's
// principle for shares): a 0-byte file was listed as "1 KB", the one file an
// engineer most needs to notice (found 9 October 2026).
export function describeFileSize(sizeBytes: number): string {
  if (sizeBytes <= 0) return "empty";
  if (sizeBytes < 1024) {
    return `${sizeBytes.toLocaleString("en-GB")} ${sizeBytes === 1 ? "byte" : "bytes"}`;
  }
  if (sizeBytes < 1024 * 1024) return `${Math.round(sizeBytes / 1024)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}
