export function savedApplicationNeedsReview(isPlanRow: boolean, planStatus: string | null): boolean {
  return isPlanRow && planStatus !== "READY";
}
