export type ApplicationCategory = "RETAIL" | "SHNI" | "SHARE" | "BHNI";

export function categoryLabel(category: string): string {
  return ({ RETAIL: "Retail", SHNI: "sHNI", SHARE: "Shareholder", BHNI: "bHNI" } as Record<string, string>)[category] ?? category;
}
