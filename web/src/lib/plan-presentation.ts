export type PlanRow = {
  ipo: string;
  applicant: string;
  category: "RETAIL" | "SHNI";
  lots: number;
  amount: string;
  demat: string;
  bank: string;
  upi: string;
  locked: boolean;
  warnings: string[];
  blocking_reasons: string[];
  reasons: { code: string; message: string }[];
};

export type PlanPreview = {
  status: "READY" | "BLOCKED";
  planned_total: string;
  rows: PlanRow[];
  uncovered: { ipo_id: string; applicant_id: string; reason: string }[];
  audit_issues: { code: string; message: string }[];
};

export function lockedMappings(rows: PlanRow[]): Pick<PlanRow, "ipo" | "applicant" | "category" | "lots" | "amount" | "demat" | "bank" | "upi">[] {
  return rows.filter((row) => row.locked).map(({ ipo, applicant, category, lots, amount, demat, bank, upi }) => ({
    ipo, applicant, category, lots, amount, demat, bank, upi,
  }));
}

export function reviewedMappings(rows: PlanRow[]): Pick<PlanRow, "ipo" | "applicant" | "category" | "lots" | "amount" | "demat" | "bank" | "upi" | "locked">[] {
  return rows.map(({ ipo, applicant, category, lots, amount, demat, bank, upi, locked }) => ({
    ipo, applicant, category, lots, amount, demat, bank, upi, locked,
  }));
}

export function rowStatus(row: PlanRow): "Ready" | "Warning" | "Blocking" {
  if (row.blocking_reasons.length) return "Blocking";
  if (row.warnings.length) return "Warning";
  return "Ready";
}

export function planStatus(plan: PlanPreview): "Ready" | "Warning" | "Blocking" {
  if (plan.status === "BLOCKED" || plan.audit_issues.length || plan.rows.some((row) => row.blocking_reasons.length)) return "Blocking";
  if (plan.rows.some((row) => row.warnings.length)) return "Warning";
  return "Ready";
}

export function canExportPlan(plan: PlanPreview): boolean {
  return planStatus(plan) !== "Blocking";
}

export function fundingLabel(row: PlanRow): string {
  return row.warnings.includes("CROSS_FUNDING") ? "Cross-funded" : "Own bank";
}

export function bankReasonSummary(row: PlanRow): string[] {
  if (row.locked || row.reasons.length === 0) return [];
  const codes = new Set(row.reasons.map((reason) => reason.code));
  const summary: string[] = [];
  if (codes.has("OWN_FUNDING")) {
    summary.push("This applicant's own bank was available.");
  } else if (codes.has("PREFERRED_CROSS_FUNDER")) {
    summary.push("The applicant's own bank could not be used, so a preferred account was chosen.");
  } else if (codes.has("OTHER_CROSS_FUNDER")) {
    summary.push("The applicant's own bank could not be used, so another allowed account was chosen.");
  }
  if (codes.has("OWNER_CASH_PROTECTED")) summary.push("The bank owner's selected IPO money remains available.");
  if (codes.has("OWNER_CASH_CONFLICT")) summary.push("This may leave the bank owner short for another selected IPO.");
  if (codes.has("ROLLING_LIMIT_ROOM")) summary.push("The bank and UPI have room for this application.");
  return summary;
}

export type DematLookup = { label: string; applicant: string; active: boolean };
export type BankLookup = { label: string; owner: string; balance: string; active: boolean; policy: string };
export type UpiLookup = { label: string; bank: string; holder: string; active: boolean; verified: boolean };
export type FundingPreference = { bank: string; priority: number; enabled: boolean };

export function splitPlanningSelections(
  selections: { ipo: string; mode: string }[],
  statuses: Record<string, string>,
): { available: { ipo: string; mode: string }[]; unavailableCount: number } {
  const available = selections.filter(({ ipo }) => ["OPEN", "UPCOMING"].includes(statuses[ipo]));
  return { available, unavailableCount: selections.length - available.length };
}

export function selectableApplicants(applicants: Record<string, { name: string; priority: number; active: boolean }>): { id: string; name: string; priority: number }[] {
  return Object.entries(applicants)
    .filter(([, applicant]) => applicant.active)
    .map(([id, applicant]) => ({ id, name: applicant.name, priority: applicant.priority }))
    .sort((a, b) => a.priority - b.priority || a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
}

export function selectableDemats(
  demats: Record<string, DematLookup>,
  applicantId: string,
): { id: string; label: string }[] {
  return Object.entries(demats)
    .filter(([, demat]) => demat.applicant === applicantId && demat.active)
    .map(([id, demat]) => ({ id, label: demat.label }))
    .sort((a, b) => a.label.localeCompare(b.label) || a.id.localeCompare(b.id));
}

export function rankedBanks(
  banks: Record<string, BankLookup>,
  upis: Record<string, UpiLookup>,
  preferences: FundingPreference[],
  applicantId: string,
): { id: string; group: "Own bank" | "Preferred cross-funding" | "Other bank"; disabled: boolean }[] {
  const rank = new Map(preferences.filter((item) => item.enabled).map((item) => [item.bank, item.priority]));
  return Object.entries(banks).map(([id, bank]) => ({
    id,
    group: bank.owner === applicantId ? "Own bank" as const : rank.has(id) ? "Preferred cross-funding" as const : "Other bank" as const,
    priority: rank.get(id) ?? Number.MAX_SAFE_INTEGER,
    disabled: !bank.active || (bank.owner !== applicantId && bank.policy === "DISALLOW") || !Object.values(upis).some((upi) => upi.bank === id && upi.active && upi.verified),
  })).sort((a, b) => {
    const groupOrder = { "Own bank": 0, "Preferred cross-funding": 1, "Other bank": 2 };
    return groupOrder[a.group] - groupOrder[b.group] || a.priority - b.priority || a.id.localeCompare(b.id);
  });
}

export function selectableUpis(
  upis: Record<string, UpiLookup>,
  bankId: string,
  applicantId: string,
): { id: string; label: string }[] {
  return Object.entries(upis)
    .filter(([, upi]) => upi.bank === bankId && upi.active && upi.verified)
    .map(([id, upi]) => ({ id, label: upi.label, own: upi.holder === applicantId }))
    .sort((a, b) => Number(b.own) - Number(a.own) || a.label.localeCompare(b.label) || a.id.localeCompare(b.id))
    .map(({ id, label }) => ({ id, label }));
}

export function rowIssueMessages(row: PlanRow): string[] {
  return [...new Set([...row.blocking_reasons, ...row.warnings])]
    .map(issueMessage)
    .filter((message, index, all) => all.indexOf(message) === index);
}

const issueMessages: Record<string, string> = {
  APPLICANT_INACTIVE: "Choose an active applicant.",
  BANK_LIMIT_EXCEEDED: "This bank has reached its application limit.",
  BANK_PAN_RESTRICTED: "This bank is restricted to another applicant.",
  CASH_OVERSPEND: "This bank needs more available money.",
  CROSS_FUNDING: "This application uses another person's funding account.",
  CROSS_FUNDING_DISALLOWED: "This bank cannot fund this applicant.",
  CROSS_FUNDING_POLICY_WARNING: "This bank's funding setting asks for a review.",
  DUPLICATE_APPLICANT_IPO: "This applicant already has an application for this IPO.",
  INSUFFICIENT_BALANCE: "This bank needs more available money.",
  INVALID_AMOUNT: "The amount does not match the chosen lots. Review the current IPO price.",
  INVALID_BANK: "Choose an active bank.",
  INVALID_CATEGORY: "Choose valid Retail or sHNI lots for this IPO.",
  INVALID_DEMAT: "Choose an active demat for this applicant.",
  INVALID_UPI: "Choose an active, verified UPI for this bank.",
  IPO_NOT_SELECTED: "Select this IPO before planning an application.",
  LOCKED_ROW_CHANGED: "A locked application changed. Review its mapping.",
  LOCKED_ROW_INFEASIBLE: "This locked mapping cannot be submitted yet. Fix the highlighted issue.",
  OWNER_CASH_CONFLICT: "This may leave the bank owner short for another selected IPO.",
  OWNER_RESERVE_TRADEOFF: "This may leave the bank owner short for another selected IPO.",
  PLANNED_TOTAL_MISMATCH: "The planned total needs to be checked again.",
  UPI_LIMIT_EXCEEDED: "This UPI has reached its application limit.",
};

export function issueMessage(code: string): string {
  return issueMessages[code] ?? "This application needs review before export.";
}
