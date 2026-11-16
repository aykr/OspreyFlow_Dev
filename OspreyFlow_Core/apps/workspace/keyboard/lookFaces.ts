// The look's own faces loaded before a harness draws, so what it measures is measured as the product draws it. Not a spec
// file: harnesses import this, never a `*.spec.ts`.
//
// `document.fonts.ready` alone resolves before any text has asked for a face, so on a cold or busy server widths were
// measured in the wider fallback (case's merge tree, 16 November 2026). And a face that cannot load must never blank the
// page: in a worktree whose node_modules is a link outside it, Vite refuses the font files, `document.fonts.load`
// rejected, and the harnesses' top-level await left them empty. So every load is caught, and none is waited on for more
// than five seconds; the page is then drawn in the fallback face, and a case that measures widths says so itself.
const GIVE_UP_MS = 5000;

export async function loadLookFaces(weights: readonly string[], also: readonly string[] = []): Promise<void> {
  const settle = (work: Promise<unknown>) =>
    Promise.race([work.catch(() => undefined), new Promise((resolve) => setTimeout(resolve, GIVE_UP_MS))]);
  try {
    const ui = getComputedStyle(document.documentElement).getPropertyValue("--ui").trim();
    const faces = [...(ui ? weights.map((weight) => `${weight} 12px ${ui}`) : []), ...also];
    await settle(Promise.all(faces.map((face) => document.fonts.load(face).catch(() => []))));
    await settle(document.fonts.ready);
  } catch {
    // A face string the browser refuses (an empty `--ui` before the stylesheet): drawn in the fallback.
  }
}
