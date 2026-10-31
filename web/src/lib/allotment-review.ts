import type { ApplicationItem } from "@/app/applications/applications-screen";
import type { RegistrarBid } from "./allotment-check";
import { isAppliedApplication } from "./applied-ipos";

export type ReviewRow = { id: string; query_id: string; application: ApplicationItem; state: string; message: string; provider: string; checked_at: string | null; records: RegistrarBid[]; matched_index: number | null; recorded: boolean; recorded_index: number | null; recorded_quantity: number | null; recorded_cost: string | null; check_available?: boolean };

export function allotmentReviewRows(items: ApplicationItem[], checked: ReviewRow[]): ReviewRow[] {
  const byId = new Map(checked.map((row) => [row.application.id, row]));
  // A check can include a bid added in another tab after the initial page load.
  const applications = new Map(items.map((item) => [item.id, item]));
  for (const row of checked) if (!applications.has(row.application.id)) applications.set(row.application.id, row.application);
  return [...applications.values()].filter(isAppliedApplication).map((item) => {
    const row = byId.get(item.id);
    const completed = ["ALLOTTED", "NOT_ALLOTTED"].includes(item.status);
    const cancelled = item.status === "CANCELLED";
    const result: ReviewRow = row ? { ...row, application: item, check_available: true } : {
      id: `unchecked-${item.id}`, query_id: "", application: item, state: "NOT_CHECKED", message: "Check this IPO to fetch the result", provider: "", checked_at: null, records: [], matched_index: null, recorded: false, recorded_index: null, recorded_quantity: null, recorded_cost: null, check_available: false,
    };
    if (completed) return { ...result, recorded: true, state: "RECORDED", message: "Result already recorded", recorded_quantity: item.allotted_quantity ?? 0, recorded_cost: item.actual_cost ?? "0.00" };
    if (cancelled) return { ...result, state: "CANCELLED", message: "Application cancelled", check_available: false };
    return result;
  }).sort((a, b) => b.application.close_date.localeCompare(a.application.close_date) || a.application.ipo_name.localeCompare(b.application.ipo_name) || a.application.applicant_name.localeCompare(b.application.applicant_name) || a.application.category.localeCompare(b.application.category));
}
