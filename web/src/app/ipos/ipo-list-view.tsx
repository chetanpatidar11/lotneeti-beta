"use client";

import { type ReactNode, useState } from "react";
import { EmptyState } from "@/components/ui";
import { matchesIPOFilters } from "./ipo-list-filter";

export type IPOListItem = {
  id: string;
  issuer: string;
  status: string;
  issueType: string;
  selected: boolean;
  skipped: boolean;
  card: ReactNode;
};

const statusOptions = [["open", "Open"], ["upcoming", "Upcoming"], ["closed", "Closed"]] as const;
const typeOptions = [["mainboard", "Mainboard"], ["sme", "SME"]] as const;
const choiceOptions = [["selected", "Selected"], ["skipped", "Skipped"]] as const;

function toggle(values: string[], value: string) {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

export default function IPOListView({ items, initialSearch = "", initialFilter = "all" }: {
  items: IPOListItem[];
  initialSearch?: string;
  initialFilter?: string;
}) {
  const [search, setSearch] = useState(initialSearch);
  const [statuses, setStatuses] = useState<string[]>(statusOptions.some(([id]) => id === initialFilter) ? [initialFilter] : []);
  const [types, setTypes] = useState<string[]>(typeOptions.some(([id]) => id === initialFilter) ? [initialFilter] : []);
  const [choices, setChoices] = useState<string[]>(choiceOptions.some(([id]) => id === initialFilter) ? [initialFilter] : []);
  const visible = items.filter((item) => matchesIPOFilters(item, search, statuses, types, choices));
  function reset() {
    setSearch(""); setStatuses([]); setTypes([]); setChoices([]);
  }
  return <>
    <div className="ipo-list-toolbar">
      <input type="search" aria-label="Search IPO issuer" placeholder="Search IPOs" value={search} onChange={(event) => setSearch(event.target.value)} />
      <button type="button" className="filter-chip" aria-pressed={!search && !statuses.length && !types.length && !choices.length} onClick={reset}>All</button>
      <span className="filter-count" role="status">{visible.length} of {items.length}</span>
    </div>
    <div className="ipo-filter-groups" aria-label="IPO filters">
      <div className="ipo-filter-group"><strong>Status</strong>{statusOptions.map(([id, label]) => <button type="button" className="filter-chip" key={id} aria-pressed={statuses.includes(id)} onClick={() => setStatuses((current) => toggle(current, id))}>{label}</button>)}</div>
      <div className="ipo-filter-group"><strong>Type</strong>{typeOptions.map(([id, label]) => <button type="button" className="filter-chip" key={id} aria-pressed={types.includes(id)} onClick={() => setTypes((current) => toggle(current, id))}>{label}</button>)}</div>
      <div className="ipo-filter-group"><strong>Choice</strong>{choiceOptions.map(([id, label]) => <button type="button" className="filter-chip" key={id} aria-pressed={choices.includes(id)} onClick={() => setChoices((current) => toggle(current, id))}>{label}</button>)}</div>
    </div>
    {visible.length ? <div className="ipo-list">{visible.map((item) => <div key={item.id}>{item.card}</div>)}</div> : <EmptyState title={items.length ? "No IPOs match these filters." : "No IPOs are available yet."} detail={items.length ? "Try another search or filter." : "Open and upcoming issues will appear after a market data sync."} action={items.length ? <button type="button" onClick={reset}>Clear filters</button> : undefined} />}
  </>;
}
