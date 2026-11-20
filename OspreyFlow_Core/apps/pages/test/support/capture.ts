import { vi } from "vitest";

export interface Captured {
  /** Everything written to the console, `process.stdout` and `process.stderr` since the capture began. */
  text(): string;
  restore(): void;
}

/**
 * Watches everything the service could write to a log: the console's methods, and `process.stdout` and
 * `process.stderr` directly. The writes still reach their destination only for the streams, never the
 * console (a test that fails shows its own output, not the service's).
 */
export function captureOutput(): Captured {
  const chunks: string[] = [];
  const spies = [
    ...(["log", "info", "warn", "error", "debug", "trace"] as const).map((method) =>
      vi.spyOn(console, method).mockImplementation((...args: unknown[]) => {
        chunks.push(args.map((a) => (typeof a === "string" ? a : JSON.stringify(a))).join(" "));
      }),
    ),
    ...([process.stdout, process.stderr] as const).map((stream) =>
      vi.spyOn(stream, "write").mockImplementation(((chunk: string | Uint8Array) => {
        chunks.push(typeof chunk === "string" ? chunk : Buffer.from(chunk).toString("utf8"));
        return true;
      }) as typeof stream.write),
    ),
  ];
  return {
    text: () => chunks.join("\n"),
    restore: () => {
      for (const spy of spies) spy.mockRestore();
    },
  };
}
