export type InvestorPriority = { id: string; planning_priority: number };

export function sortByPriority<T extends InvestorPriority>(investors: T[]): T[] {
  return [...investors].sort(
    (a, b) => a.planning_priority - b.planning_priority || a.id.localeCompare(b.id),
  );
}

export function movePriority<T extends InvestorPriority>(investors: T[], index: number, step: -1 | 1): T[] {
  const ordered = [...investors];
  const next = index + step;
  if (next < 0 || next >= ordered.length) return ordered;
  [ordered[index], ordered[next]] = [ordered[next], ordered[index]];
  return ordered.map((item, position) => ({ ...item, planning_priority: position + 1 }));
}
