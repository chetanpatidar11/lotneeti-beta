type LinkedUpi = { id: string; holder: string; bank_id: string };

export function reassignBankUpis<D, U extends LinkedUpi>(
  accounts: Record<string, { demats: D[]; upis: U[] }>,
  bankId: string,
  holderId: string,
): Record<string, { demats: D[]; upis: U[] }> {
  const moved = Object.values(accounts).flatMap((group) => group.upis)
    .filter((upi) => upi.bank_id === bankId).map((upi) => ({ ...upi, holder: holderId }));
  if (moved.length === 0) return accounts;
  const next = Object.fromEntries(Object.entries(accounts).map(([id, group]) => [id, {
    ...group, upis: group.upis.filter((upi) => upi.bank_id !== bankId),
  }]));
  const destination = next[holderId] ?? { demats: [], upis: [] };
  next[holderId] = { ...destination, upis: [...destination.upis, ...moved] };
  return next;
}
