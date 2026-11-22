// The browser's half of opening a guide (ADR-145 Amendment 10): a blank tab (`window.open`) and a saved file (an
// `<a download>` clicked), which the shared package's `openGuide` takes as its two required dependencies so that it
// holds no `window` or `document` (ADR-152 R2, PL4 slice D3e). `openGuide` here is the package's, with those two supplied;
// a caller may still hand in its own.
import { openGuide as openGuideWith, type GuideId, type OpenGuideDeps } from "@ospreyflow/glass-shared";

export function saveAs(url: string, name: string): void {
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.rel = "noopener";
  link.style.display = "none";
  document.body.append(link);
  link.click();
  link.remove();
}

/** A blank tab, opened while the person's click still counts as their own. */
export function openBlankTab(): Window | null {
  return window.open("", "_blank");
}

export type BrowserGuideDeps = Omit<OpenGuideDeps, "openTab" | "save"> & Partial<Pick<OpenGuideDeps, "openTab" | "save">>;

/** Opens a guide in the browser: the package's `openGuide`, given this file's tab and download. */
export function openGuide(guide: GuideId, deps: BrowserGuideDeps): Promise<string | null> {
  return openGuideWith(guide, { ...deps, openTab: deps.openTab ?? openBlankTab, save: deps.save ?? saveAs });
}
