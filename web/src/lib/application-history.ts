import { formatInr } from "./money";

export type ApplicationHistoryInput = {
  amount: string;
  status: "PLANNED" | "SUBMITTED" | "BLOCKED" | "ALLOTTED" | "NOT_ALLOTTED";
  planned_at: string;
  submitted_at: string | null;
  blocked_at: string | null;
  result_at: string | null;
  allotted_quantity: number | null;
  actual_cost: string | null;
};

export type ApplicationHistoryEvent = { at: string; label: string };

export function applicationHistory(item: ApplicationHistoryInput): ApplicationHistoryEvent[] {
  const events: ApplicationHistoryEvent[] = [{ at: item.planned_at, label: "Added to plan" }];
  if (item.submitted_at) {
    events.push({ at: item.submitted_at, label: `Submitted for ${formatInr(item.amount)}` });
  }
  if (item.blocked_at) {
    events.push({ at: item.blocked_at, label: `${formatInr(item.amount)} blocked` });
  }
  if (item.result_at && item.status === "NOT_ALLOTTED") {
    events.push({ at: item.result_at, label: "Not allotted" });
    events.push({ at: item.result_at, label: `${formatInr(item.amount)} released from Blocked; Balance unchanged` });
  }
  if (item.result_at && item.status === "ALLOTTED" && item.actual_cost !== null) {
    events.push({ at: item.result_at, label: `Allotted ${item.allotted_quantity} shares` });
    events.push({ at: item.result_at, label: `${formatInr(item.actual_cost)} deducted from Balance` });
    events.push({ at: item.result_at, label: `${formatInr(item.amount)} released from Blocked` });
  }
  return events;
}
