export type IPOFilterItem = {
  issuer: string;
  status: string;
  issueType: string;
  selected: boolean;
  skipped: boolean;
};

export function matchesIPOFilters(item: IPOFilterItem, search: string, statuses: string[], types: string[], choices: string[]) {
  const query = search.trim().toLocaleLowerCase("en-IN");
  const status = ["CLOSED", "ALLOTMENT", "LISTED"].includes(item.status) ? "closed" : item.status.toLowerCase();
  return (!query || item.issuer.toLocaleLowerCase("en-IN").includes(query))
    && (statuses.length === 0 || statuses.includes(status))
    && (types.length === 0 || types.includes(item.issueType.toLowerCase()))
    && (choices.length === 0 || (choices.includes("selected") && item.selected) || (choices.includes("skipped") && item.skipped));
}
