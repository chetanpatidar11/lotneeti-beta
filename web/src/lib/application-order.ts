type ApplicationTime = { id: string; planned_at: string; submitted_at: string | null };

export function newestApplicationFirst(left: ApplicationTime, right: ApplicationTime): number {
  return Date.parse(right.submitted_at ?? right.planned_at) - Date.parse(left.submitted_at ?? left.planned_at)
    || Date.parse(right.planned_at) - Date.parse(left.planned_at)
    || right.id.localeCompare(left.id);
}
