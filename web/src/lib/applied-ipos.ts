export type AppliedIpoInput = { ipo: string; ipo_name: string; close_date: string; is_plan_row: boolean; status: string; submitted_at: string | null };
export type AppliedIpoSummary = { id: string; name: string; closeDate: string; total: number; pending: number; allotted: number; notAllotted: number; cancelled: number };

export function isAppliedApplication(item: Pick<AppliedIpoInput, "is_plan_row" | "status" | "submitted_at">): boolean {
  return !item.is_plan_row && (Boolean(item.submitted_at) || ["SUBMITTED", "BLOCKED", "ALLOTTED", "NOT_ALLOTTED"].includes(item.status));
}

export function appliedIpos(items: AppliedIpoInput[]): AppliedIpoSummary[] {
  const groups = new Map<string, AppliedIpoSummary>();
  for (const item of items.filter(isAppliedApplication)) {
    const summary = groups.get(item.ipo) ?? { id: item.ipo, name: item.ipo_name, closeDate: item.close_date, total: 0, pending: 0, allotted: 0, notAllotted: 0, cancelled: 0 };
    summary.total += 1;
    if (["SUBMITTED", "BLOCKED"].includes(item.status)) summary.pending += 1;
    if (item.status === "ALLOTTED") summary.allotted += 1;
    if (item.status === "NOT_ALLOTTED") summary.notAllotted += 1;
    if (item.status === "CANCELLED") summary.cancelled += 1;
    groups.set(item.ipo, summary);
  }
  return [...groups.values()].sort((a, b) => b.closeDate.localeCompare(a.closeDate) || a.name.localeCompare(b.name));
}
