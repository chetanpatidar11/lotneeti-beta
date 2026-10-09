"use client";

import { FormEvent, useState } from "react";

export type BankOption = {
  id: string;
  owner: string;
  bank_name: string;
  account_masked: string;
  current_balance: string;
  active: boolean;
};

export type FundingPreference = {
  id: string;
  bank: string;
  priority: number;
  enabled: boolean;
};

type InvestorOption = { id: string; name: string };

function ordered(items: FundingPreference[]) {
  return [...items].sort((a, b) => a.priority - b.priority || a.bank.localeCompare(b.bank));
}

export default function PreferredFunding({
  workspaceId,
  investor,
  investors,
  banks,
  initialPreferences,
  canEdit,
}: {
  workspaceId: string;
  investor: InvestorOption;
  investors: InvestorOption[];
  banks: BankOption[];
  initialPreferences: FundingPreference[];
  canEdit: boolean;
}) {
  const [preferences, setPreferences] = useState(ordered(initialPreferences));
  const [selectedBank, setSelectedBank] = useState("");
  const [message, setMessage] = useState("");
  const [messageError, setMessageError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [orderChanged, setOrderChanged] = useState(false);
  const base = `/api/workspaces/${workspaceId}/investors/${investor.id}/funding-preferences`;
  const ownBanks = banks.filter((bank) => bank.owner === investor.id && bank.active);
  const available = banks.filter((bank) => bank.owner !== investor.id && bank.active && !preferences.some((item) => item.bank === bank.id));

  function bankLabel(bank: BankOption) {
    return `${investors.find((person) => person.id === bank.owner)?.name ?? "Investor"} · ${bank.bank_name} ${bank.account_masked}`;
  }

  function note(text: string, error = false) {
    setMessage(text);
    setMessageError(error);
  }

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedBank) return;
    setBusy(true);
    try {
      const response = await fetch(base, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ bank: selectedBank, priority: Math.max(0, ...preferences.map((item) => item.priority)) + 1 }),
      });
      if (!response.ok) throw new Error("Save failed");
      setPreferences(ordered([...preferences, (await response.json()) as FundingPreference]));
      setSelectedBank("");
      note("Preferred account added.");
    } catch {
      note("We could not add this account. Please try again.", true);
    } finally {
      setBusy(false);
    }
  }

  async function update(id: string, changes: Partial<FundingPreference>) {
    setBusy(true);
    try {
      const response = await fetch(`${base}/${id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(changes),
      });
      if (!response.ok) throw new Error("Save failed");
      const saved = (await response.json()) as FundingPreference;
      setPreferences((current) => ordered(current.map((item) => item.id === id ? saved : item)));
      note("Preferred account updated.");
    } catch {
      note("We could not save this account. Please try again.", true);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    try {
      const response = await fetch(`${base}/${id}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Delete failed");
      setPreferences((current) => current.filter((item) => item.id !== id));
      note("Preferred account removed.");
    } catch {
      note("We could not remove this account. Please try again.", true);
    } finally {
      setBusy(false);
    }
  }

  function movePreference(index: number, direction: -1 | 1) {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= preferences.length) return;
    const reordered = [...preferences];
    [reordered[index], reordered[targetIndex]] = [reordered[targetIndex], reordered[index]];
    setPreferences(reordered.map((item, itemIndex) => ({ ...item, priority: itemIndex + 1 })));
    setOrderChanged(true);
    note("");
  }

  async function saveOrder() {
    setBusy(true);
    try {
      const saved: FundingPreference[] = [];
      for (const item of preferences) {
        const response = await fetch(`${base}/${item.id}`, {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ priority: item.priority }),
        });
        if (!response.ok) throw new Error("Save failed");
        saved.push(await response.json() as FundingPreference);
      }
      setPreferences(ordered(saved));
      setOrderChanged(false);
      note("Preferred account order saved.");
    } catch {
      note("We could not save this order. Please try again.", true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="preferred-funding" aria-label={`Preferred funding accounts for ${investor.name}`}>
      <div className="preferred-funding-heading">
        <div>
          <h3>Preferred funding accounts</h3>
          <p>Own accounts are considered first. Other accounts follow this order when needed.</p>
        </div>
        {canEdit && preferences.length > 0 && <button type="button" className="button-secondary" disabled={busy || !orderChanged} onClick={() => void saveOrder()}>Save order</button>}
      </div>
      {ownBanks.length > 0 && <ul className="own-bank-list" aria-label="Own accounts considered first">
        {ownBanks.map((bank) => <li key={bank.id}><span>{bankLabel(bank)}</span><small>Own account · first choice</small></li>)}
      </ul>}
      {preferences.length > 0 ? <ol className="preference-list">
        {preferences.map((item, index) => {
          const bank = banks.find((option) => option.id === item.bank);
          const label = bank ? bankLabel(bank) : "unavailable account";
          return <li key={item.id}>
            <div className="preference-account">
              <div className="preference-rank" aria-label={`Priority ${item.priority}`}>{item.priority}</div>
              <div><strong>{bank ? bankLabel(bank) : "Account unavailable"}</strong><small>{item.enabled ? "Preferred fallback" : "Paused"}</small></div>
            </div>
            {canEdit && <div className="preference-actions">
              <span className="settings-order">
                <button type="button" className="button-secondary" aria-label={`Move ${label} up`} disabled={busy || index === 0} onClick={() => movePreference(index, -1)}>↑</button>
                <button type="button" className="button-secondary" aria-label={`Move ${label} down`} disabled={busy || index === preferences.length - 1} onClick={() => movePreference(index, 1)}>↓</button>
              </span>
              <label className="preference-enabled"><input type="checkbox" aria-label={`Enable ${label}`} checked={item.enabled} disabled={busy} onChange={(event) => update(item.id, { enabled: event.target.checked })} /> Enabled</label>
              <button type="button" className="button-ghost-danger" aria-label={`Remove ${label}`} disabled={busy} onClick={() => remove(item.id)}>Remove</button>
            </div>}
          </li>;
        })}
      </ol> : <p className="preference-empty">No preferred accounts yet. Add one below to set a fallback.</p>}
      {canEdit && available.length > 0 && <form onSubmit={add} className="preference-add">
        <div><strong>Add an account</strong><p>Choose an active account from another investor.</p></div>
        <label htmlFor={`preferred-bank-${investor.id}`}>Account
          <select id={`preferred-bank-${investor.id}`} value={selectedBank} onChange={(event) => setSelectedBank(event.target.value)} required>
            <option value="">Choose account</option>
            {available.map((bank) => <option key={bank.id} value={bank.id}>{bankLabel(bank)}</option>)}
          </select>
        </label>
        <button type="submit" disabled={busy || !selectedBank}>Add preferred account</button>
      </form>}
      <p className="preference-note">Other allowed accounts remain available if preferred accounts cannot be used.</p>
      {message && <p className={messageError ? "preference-message error" : "preference-message"} role={messageError ? "alert" : "status"}>{message}</p>}
    </section>
  );
}
