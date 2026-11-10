// A vitest reporter that ends each run with its slowest tests (admin's T1 part 1), as pytest's --durations=30
// does for the Python suites, so every log names where its time went. It prints only; it never changes a result.
// Used by apps/workspace's and apps/harness's vitest.config.ts beside the default reporter.

interface CaseLike {
  readonly fullName: string;
  diagnostic(): { readonly duration: number } | undefined;
}
interface ModuleLike {
  readonly relativeModuleId: string;
  readonly children: { allTests(): Iterable<CaseLike> };
}

export const SLOWEST = 30;

/** The run's `n` slowest tests, slowest first, by file and full name; tests not run are left out. */
export function slowestLines(modules: readonly ModuleLike[], n: number): string[] {
  const all: [number, string][] = [];
  for (const m of modules)
    for (const t of m.children.allTests()) {
      const d = t.diagnostic();
      if (d !== undefined) all.push([d.duration, `${m.relativeModuleId} > ${t.fullName}`]);
    }
  if (all.length === 0) return [];
  all.sort((a, b) => b[0] - a[0]);
  const kept = all.slice(0, n);
  const head = kept.length < all.length ? `Slowest ${kept.length} of ${all.length} tests:` : `Slowest ${all.length} tests:`;
  return [head, ...kept.map(([ms, name]) => `${String(Math.round(ms)).padStart(6)} ms  ${name}`)];
}

export default class SlowestReporter {
  onTestRunEnd(modules: readonly ModuleLike[]): void {
    const lines = slowestLines(modules, SLOWEST);
    if (lines.length > 0) process.stdout.write(`\n${lines.join("\n")}\n`);
  }
}
