import { amountForLots, minimumShniLots } from "./plan-amount";

type AllotmentTerms = { category: string; lots: number; lot_size: number; upper_price: string; max_quantity: number };

export function defaultAllotmentShares(item: AllotmentTerms): number | null {
  if (item.category === "SHARE") return null;
  if (!Number.isSafeInteger(item.lot_size) || item.lot_size < 1 || !Number.isSafeInteger(item.lots) || item.lots < 1) return null;
  try {
    const lots = item.category === "RETAIL" ? 1 : item.category === "SHNI" ? item.lots
      : item.category === "BHNI" ? minimumShniLots(item.upper_price, item.lot_size) : 0;
    const quantity = lots * item.lot_size;
    return Number.isSafeInteger(quantity) && quantity > 0 && quantity <= item.max_quantity ? quantity : null;
  } catch {
    return null;
  }
}

export function validAllotmentAmount(amount: string, blockedAmount: string): boolean {
  return /^\d+(?:\.\d{1,2})?$/.test(amount) && Number(amount) > 0 && Number(amount) <= Number(blockedAmount);
}

export function applicationResultAmount(upperPrice: string, quantity: number, maxQuantity: number): string | null {
  if (!Number.isSafeInteger(quantity) || quantity < 1 || quantity > maxQuantity) return null;
  try {
    return amountForLots(upperPrice, 1, quantity);
  } catch {
    return null;
  }
}
