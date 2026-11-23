// Harness pages do not run `src/main.tsx`, so `?brand=govuk` is applied here instead (ADR-132). With
// no `?brand=` it leaves a page exactly as before: it sets `data-brand="ospreyflow"`, which nothing
// styles. The GOV.UK identity (ADR-152 decision 14) is on here unless `?govuk_identity=off`: the specs measure the GOV.UK
// look with its typeface, which the Playwright servers' sync step copies (`OSPREY_GOVUK_IDENTITY=1` in each config).
// Not a spec file: harnesses import this, never a `*.spec.ts`.
import { applyBrand, brandFromUrl, identityFromUrl, loadBrandStylesheet, applyTheme } from "@ospreyflow/glass-shared";

export async function applyHarnessBrand(): Promise<"govuk" | "ospreyflow"> {
  const brand = brandFromUrl(window.location.search, true) ?? "ospreyflow";
  applyBrand(brand, identityFromUrl(window.location.search, true) ?? true);
  if (brand === "govuk") applyTheme("light");
  await loadBrandStylesheet(brand);
  return brand;
}
