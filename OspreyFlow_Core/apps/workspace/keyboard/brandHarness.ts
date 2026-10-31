// Harness pages do not run `src/main.tsx`, so `?brand=govuk` is applied here instead (ADR-132). With
// no `?brand=` it leaves a page exactly as before: it sets `data-brand="ospreyflow"`, which nothing
// styles. Not a spec file: harnesses import this, never a `*.spec.ts`.
import { applyBrand, brandFromUrl, loadBrandStylesheet } from "../src/brand/brand";
import { applyTheme } from "../src/theme/theme";

export async function applyHarnessBrand(): Promise<"govuk" | "ospreyflow"> {
  const brand = brandFromUrl(window.location.search, true) ?? "ospreyflow";
  applyBrand(brand);
  if (brand === "govuk") applyTheme("light");
  await loadBrandStylesheet(brand);
  return brand;
}
