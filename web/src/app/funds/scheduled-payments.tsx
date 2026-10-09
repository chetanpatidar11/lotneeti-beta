"use client";

import { FormEvent, useEffect, useState } from "react";
import { formatInr } from "@/lib/money";
import { Drawer } from "@/components/drawer";
import { EmptyState, StatusBadge } from "@/components/ui";

export type ScheduledPayment = {
  id: string;
  name: string;
  amount: string;
  frequency: "DAILY" | "WEEKLY" | "MONTHLY";
  start_date: string;
  next_due_date: string;
  end_date: string | null;
  active: boolean;
};

const emptyForm = {
  name: "",
  amount: "",
  frequency: "MONTHLY" as ScheduledPayment["frequency"],
  start_date: "",
  next_due_date: "",
  end_date: "",
};

export default function ScheduledPayments({
  workspaceId,
  bankId,
  canEdit,
  initialPayments,
}: {
  workspaceId: string;
  bankId: string;
  canEdit: boolean;
  initialPayments: ScheduledPayment[];
}) {
  const [payments, setPayments] = useState(initialPayments);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const base = `/api/workspaces/${workspaceId}/banks/${bankId}/recurring-debits`;

  useEffect(() => {
    let cancelled = false;
    fetch(base).then(async (response) => {
      if (response.ok && !cancelled) setPayments((await response.json()) as ScheduledPayment[]);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [base]);

  function startEdit(payment: ScheduledPayment) {
    setFormOpen(true);
    setEditingId(payment.id);
    setForm({
      name: payment.name,
      amount: payment.amount,
      frequency: payment.frequency,
      start_date: payment.start_date,
      next_due_date: payment.next_due_date,
      end_date: payment.end_date ?? "",
    });
    setMessage("");
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const payload = {
      ...form,
      next_due_date: editingId ? form.next_due_date : form.start_date,
      end_date: form.end_date || null,
    };
    try {
      const response = await fetch(editingId ? `${base}/${editingId}` : base, {
        method: editingId ? "PATCH" : "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Save failed");
      const payment = (await response.json()) as ScheduledPayment;
      setPayments(editingId ? payments.map((item) => item.id === payment.id ? payment : item) : [...payments, payment]);
      setEditingId(null);
      setForm(emptyForm);
      setFormOpen(false);
      setMessage("Scheduled payment saved.");
    } catch {
      setMessage("Check the payment details and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(payment: ScheduledPayment) {
    setBusy(true);
    try {
      const response = await fetch(`${base}/${payment.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ active: !payment.active }),
      });
      if (!response.ok) throw new Error("Update failed");
      const updated = (await response.json()) as ScheduledPayment;
      setPayments(payments.map((item) => item.id === updated.id ? updated : item));
      setMessage(updated.active ? "Scheduled payment resumed." : "Scheduled payment paused.");
    } catch {
      setMessage("We could not update this payment.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(payment: ScheduledPayment) {
    setBusy(true);
    try {
      const response = await fetch(`${base}/${payment.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Delete failed");
      setPayments(payments.filter((item) => item.id !== payment.id));
      if (editingId === payment.id) { setEditingId(null); setForm(emptyForm); }
      setMessage("Scheduled payment deleted.");
    } catch {
      setMessage("We could not delete this payment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="scheduled-payments">
      {canEdit && <button type="button" className="button-secondary" onClick={() => { setEditingId(null); setForm(emptyForm); setFormOpen(true); }}>+ Add payment</button>}
      {payments.length === 0 ? <EmptyState title="No scheduled payments." detail="Upcoming debits will appear here." /> : (
        <ul className="change-list">
          {payments.map((payment) => (
            <li key={payment.id}>
              <span><strong>{payment.name}</strong><br /><small>{payment.frequency.toLowerCase()} · Next {payment.next_due_date}</small> <StatusBadge tone={payment.active ? "positive" : "neutral"}>{payment.active ? "Active" : "Paused"}</StatusBadge></span>
              <span>{formatInr(payment.amount)}<br />
                {canEdit && <span className="payment-buttons">
                  <button type="button" aria-label={`Edit ${payment.name}`} disabled={busy} onClick={() => startEdit(payment)}>Edit</button>
                  <button type="button" aria-label={`${payment.active ? "Pause" : "Resume"} ${payment.name}`} disabled={busy} onClick={() => toggleActive(payment)}>{payment.active ? "Pause" : "Resume"}</button>
                  <button type="button" aria-label={`Delete ${payment.name}`} disabled={busy} onClick={() => remove(payment)}>Delete</button>
                </span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      {canEdit && formOpen && <Drawer title={editingId ? "Edit scheduled payment" : "Add scheduled payment"} onClose={() => setFormOpen(false)}>
        <form onSubmit={save} className="sign-in-form add-investor-form">
          <label htmlFor="payment-name">Name</label>
          <input id="payment-name" required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
          <label htmlFor="payment-amount">Amount (₹)</label>
          <input id="payment-amount" type="number" min="0.01" step="0.01" required value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} />
          <label htmlFor="payment-frequency">Repeat</label>
          <select id="payment-frequency" value={form.frequency} onChange={(event) => setForm({ ...form, frequency: event.target.value as ScheduledPayment["frequency"] })}>
            <option value="DAILY">Daily</option><option value="WEEKLY">Weekly</option><option value="MONTHLY">Monthly</option>
          </select>
          <label htmlFor="payment-start">Start date</label>
          <input id="payment-start" type="date" required value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} />
          {editingId && <><label htmlFor="payment-next">Next payment date</label><input id="payment-next" type="date" required value={form.next_due_date} onChange={(event) => setForm({ ...form, next_due_date: event.target.value })} /></>}
          <label htmlFor="payment-end">End date (optional)</label>
          <input id="payment-end" type="date" value={form.end_date} onChange={(event) => setForm({ ...form, end_date: event.target.value })} />
          <button type="submit" disabled={busy}>{editingId ? "Save changes" : "Add scheduled payment"}</button>
          {editingId && <button type="button" className="button-secondary" disabled={busy} onClick={() => { setEditingId(null); setForm(emptyForm); setFormOpen(false); }}>Cancel edit</button>}
        </form>
      </Drawer>}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
