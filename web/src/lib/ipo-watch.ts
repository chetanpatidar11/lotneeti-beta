const planningFactLabels: Record<string, string> = {
  lower_price: "lower price",
  upper_price: "upper price",
  lot_size: "lot size",
  open_date: "open date",
  close_date: "close date",
  allotment_date: "allotment date",
};

export function missingPlanningFacts(fields: string[]): string {
  if (fields.length === 0) return "Planning review pending";
  return `Planning unavailable · Missing: ${fields.map((field) => planningFactLabels[field] ?? "required issue fact").join(", ")}`;
}

export function watchPlanningMessage(issue: {
  enrichment_state: "DISCOVERED" | "ENRICHING" | "REVIEW_REQUIRED" | "READY";
  missing_planning_fields: string[];
  review_reasons?: string[];
  source_conflict_fields?: string[];
}): string {
  if (issue.enrichment_state === "DISCOVERED") return "Issue details not fetched yet";
  if (issue.enrichment_state === "ENRICHING") return "Official document enrichment pending";
  if (issue.enrichment_state === "READY") return "Issue facts ready · Founder publication pending";
  if (issue.source_conflict_fields?.length) return "Exchange values conflict · Founder review required";
  if (issue.missing_planning_fields.length) {
    return `${missingPlanningFacts(issue.missing_planning_fields)} · Official source review required`;
  }
  return issue.review_reasons?.[0] ?? "Founder review required";
}
