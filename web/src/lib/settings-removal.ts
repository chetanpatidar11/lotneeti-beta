export type SettingsKind = "investor" | "demat" | "bank" | "upi";
export type SettingsAction = "remove" | "restore";

type ActiveItem = { id: string; active: boolean };
type BankItem = ActiveItem & { owner: string };
type UpiItem = ActiveItem & { holder: string; bank_id: string };

export type AccountState<
  I extends ActiveItem,
  B extends BankItem,
  D extends ActiveItem,
  U extends UpiItem,
> = {
  investors: I[];
  banks: B[];
  linkedAccounts: Record<string, { demats: D[]; upis: U[] }>;
};

function setActive<T extends ActiveItem>(items: T[], ids: Set<string>, active: boolean): T[] {
  return items.map((item) => ids.has(item.id) ? { ...item, active } : item);
}

export function toggleSelected(current: string[], id: string, checked: boolean): string[] {
  return checked ? [...new Set([...current, id])] : current.filter((value) => value !== id);
}

export function applySettingsAction<
  I extends ActiveItem,
  B extends BankItem,
  D extends ActiveItem,
  U extends UpiItem,
>(state: AccountState<I, B, D, U>, kind: SettingsKind, values: string[], action: SettingsAction): AccountState<I, B, D, U> {
  const ids = new Set(values);
  const active = action === "restore";
  const removingInvestor = kind === "investor" && !active;
  const removingBank = kind === "bank" && !active;
  const childBankIds = new Set(state.banks.filter((bank) => removingInvestor && ids.has(bank.owner)).map((bank) => bank.id));
  const banksToChange = removingInvestor ? childBankIds : kind === "bank" ? ids : new Set<string>();

  return {
    investors: kind === "investor" ? setActive(state.investors, ids, active) : state.investors,
    banks: banksToChange.size ? setActive(state.banks, banksToChange, active) : state.banks,
    linkedAccounts: Object.fromEntries(Object.entries(state.linkedAccounts).map(([owner, accounts]) => [owner, {
      demats: kind === "demat" ? setActive(accounts.demats, ids, active)
        : removingInvestor && ids.has(owner) ? setActive(accounts.demats, new Set(accounts.demats.map((item) => item.id)), false)
          : accounts.demats,
      upis: accounts.upis.map((upi) => {
        const selected = kind === "upi" && ids.has(upi.id);
        const cascaded = (removingInvestor && (ids.has(upi.holder) || childBankIds.has(upi.bank_id)))
          || (removingBank && ids.has(upi.bank_id));
        return selected || cascaded ? { ...upi, active: cascaded ? false : active } : upi;
      }),
    }])),
  };
}
