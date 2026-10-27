export type PortfolioTab = "holdings" | "results" | "sales";

export const portfolioTabs: { id: PortfolioTab; label: string }[] = [
  { id: "holdings", label: "Allotted holdings" },
  { id: "results", label: "Realized results" },
  { id: "sales", label: "Recorded sales" },
];

export function portfolioTab(value?: string, hasPeriod = false): PortfolioTab {
  return portfolioTabs.some((tab) => tab.id === value) ? value as PortfolioTab : hasPeriod ? "results" : "holdings";
}

export function portfolioTabHref(tab: PortfolioTab, fromDate = "", toDate = ""): string {
  const params = new URLSearchParams({ tab });
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);
  return `/portfolio?${params}`;
}
