export function indiaSaleDate(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

export function unsoldShares(applicationId: string, allotted: number | null, sales: { application: string; quantity: number }[]): number {
  return Math.max(0, (allotted ?? 0) - sales.filter((sale) => sale.application === applicationId).reduce((total, sale) => total + sale.quantity, 0));
}

function money(paise: bigint): string {
  return `${paise / 100n}.${(paise % 100n).toString().padStart(2, "0")}`;
}

function roundedRate(paise: bigint, numerator: bigint, denominator: bigint): bigint {
  return (paise * numerator + denominator / 2n) / denominator;
}

// User-supplied NSE delivery sell rates. These are editable estimates, not broker bills.
export function estimatedSaleCharges(price: string, quantity: number) {
  if (!/^\d+(?:\.\d{1,2})?$/.test(price) || !Number.isSafeInteger(quantity) || quantity < 1) return null;
  const [whole, fraction = ""] = price.split(".");
  const pricePaise = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  if (pricePaise <= 0n) return null;
  const turnover = pricePaise * BigInt(quantity);
  const dp = 1534n;
  const stt = roundedRate(turnover, 1n, 1000n);
  const exchange = roundedRate(turnover, 345n, 10000000n);
  const sebi = roundedRate(turnover, 1n, 1000000n);
  const gst = roundedRate(exchange + sebi, 18n, 100n);
  return {
    turnover: money(turnover), brokerage: "0.00", dp: money(dp), stt: money(stt),
    exchange: money(exchange), gst: money(gst), sebi: money(sebi), stamp: "0.00",
    total: money(dp + stt + exchange + gst + sebi),
  };
}
