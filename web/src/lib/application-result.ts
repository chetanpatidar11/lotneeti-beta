import { amountForLots } from "./plan-amount";

export function applicationResultAmount(upperPrice: string, quantity: number, maxQuantity: number): string | null {
  if (!Number.isSafeInteger(quantity) || quantity < 1 || quantity > maxQuantity) return null;
  try {
    return amountForLots(upperPrice, 1, quantity);
  } catch {
    return null;
  }
}
