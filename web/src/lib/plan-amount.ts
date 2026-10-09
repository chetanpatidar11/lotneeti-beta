function parseCents(value: string): bigint {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value)) throw new Error("Invalid amount");
  const [whole, fraction = ""] = value.split(".");
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  return cents;
}

function priceCents(upperPrice: string): bigint {
  const cents = parseCents(upperPrice);
  if (cents <= 0n) throw new Error("Invalid IPO price");
  return cents;
}

function centsToString(cents: bigint): string {
  const whole = cents / 100n;
  const fraction = (cents % 100n).toString().padStart(2, "0");
  return `${whole}.${fraction}`;
}

export function minimumShniLots(upperPrice: string, lotSize: number): number {
  if (!Number.isSafeInteger(lotSize) || lotSize < 1) throw new Error("Invalid lot size");
  return Number(20000000n / (priceCents(upperPrice) * BigInt(lotSize)) + 1n);
}

export function amountForLots(upperPrice: string, lotSize: number, lots: number): string {
  if (!Number.isSafeInteger(lotSize) || lotSize < 1 || !Number.isSafeInteger(lots) || lots < 1) {
    throw new Error("Invalid lots");
  }
  const cents = priceCents(upperPrice) * BigInt(lotSize) * BigInt(lots);
  return centsToString(cents);
}

export function sumAmounts(values: string[]): string {
  return centsToString(values.reduce((sum, value) => sum + parseCents(value), 0n));
}
