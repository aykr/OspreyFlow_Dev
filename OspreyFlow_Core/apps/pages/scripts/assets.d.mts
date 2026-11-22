export const ALLOWED_DRAWING: string[];

export interface FontEntry {
  family: string;
  role: string;
  source: string;
  weights: number[];
  licence: string;
  only_when?: string;
  only_on?: string;
}

export function defaultFaces(list: { fonts: FontEntry[] }): FontEntry[];
export function withoutGovukBrand(css: string): string;
export function buildAssets(options: {
  outDir: string;
  modulesDir?: string;
  extraStylesheets?: string[];
}): Promise<{ manifest: Record<string, string>; outDir: string }>;
export function identityPattern(list: { fonts: (FontEntry & { self_hosted_under?: string })[] }): RegExp;
