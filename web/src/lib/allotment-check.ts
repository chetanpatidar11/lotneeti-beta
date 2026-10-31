import { applicationResultAmount, validAllotmentAmount } from "./application-result";

export type RegistrarBid = { quantity: number; applied: number | null; reference: string; demat: string; category: string };
export type AllotmentDraft = { quantity: string; cost: string; sourceIndex: string; manualVerified: boolean; selected: boolean; dirty: boolean };
export type AllotmentApplication = { upper_price: string; max_quantity: number; amount: string; lot_size: number };

export function checkedAmount(item: AllotmentApplication, quantity: string): string {
  if (!/^\d+$/.test(quantity)) return "";
  if (Number(quantity) === 0) return "0.00";
  return applicationResultAmount(item.upper_price, Number(quantity), item.max_quantity) ?? "";
}

export function initialCheckedDraft(item: AllotmentApplication, bids: RegistrarBid[], index: number | null): AllotmentDraft {
  const quantity = index !== null && bids[index] ? String(bids[index].quantity) : "";
  return { quantity, cost: checkedAmount(item, quantity), sourceIndex: index === null ? "" : String(index), manualVerified: false, selected: false, dirty: false };
}

export function validCheckedDraft(item: AllotmentApplication, draft: AllotmentDraft, matchedIndex: number | null): boolean {
  if (!/^\d+$/.test(draft.quantity)) return false;
  const shares = Number(draft.quantity);
  if (!Number.isSafeInteger(shares) || shares > item.max_quantity) return false;
  if (shares === 0 ? !/^0(?:\.0{1,2})?$/.test(draft.cost) : !validAllotmentAmount(draft.cost, item.amount)) return false;
  return matchedIndex !== null && draft.sourceIndex === String(matchedIndex) || draft.manualVerified;
}
