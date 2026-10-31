export const goldForms = { COIN: "Coin", BAR: "Bar", JEWELLERY: "Jewellery", OTHER: "Other physical gold" } as const;
export type GoldPurchase = {
  id: string; name: string; form: keyof typeof goldForms; owner_name: string; purity: string;
  purchased_on: string; grams: string; total_cost: string; sold_grams: string; remaining_grams: string;
  remaining_cost: string; current_price_per_gram: string | null; price_updated_at: string | null;
  estimated_value: string | null; unrealized_profit: string | null; seller: string; notes: string; removed: boolean;
};
export type GoldSale = {
  id: string; purchase: string; name: string; owner_name: string; purity: string; sold_on: string;
  grams: string; net_proceeds: string; allocated_cost: string | null; realized_profit: string | null;
  notes: string; removed: boolean;
};
export type GoldReport = {
  purchases: GoldPurchase[]; sales: GoldSale[];
  summary: {
    purchase_count: number; grams_held: string; cost_of_holdings: string; total_paid: string;
    net_sale_receipts: string; realized_profit: string; estimated_value: string | null;
    unrealized_profit: string | null; priced_value: string; unpriced_holdings: number;
  };
};
export function goldGrams(value: string): string {
  const [whole, fraction = ""] = value.split(".");
  const trimmed = fraction.replace(/0+$/, "");
  return `${whole}${trimmed ? `.${trimmed}` : ""}`;
}
export function goldDate(value: string): string {
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric", timeZone: "Asia/Kolkata" }).format(new Date(value.includes("T") ? value : `${value}T12:00:00+05:30`));
}
export function goldError(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(goldError).join(" ");
  if (value && typeof value === "object") return Object.entries(value).map(([key, item]) => `${key === "detail" || key === "message" ? "" : `${key.replaceAll("_", " ")}: `}${goldError(item)}`).join(" ");
  return "Unable to save this gold record. Please try again.";
}
export function filterGold<T extends { name: string; owner_name: string; purity: string; notes: string; removed: boolean; seller?: string }>(items: T[], query: string, showRemoved: boolean): T[] {
  const search = query.trim().toLocaleLowerCase("en-IN");
  return items.filter((item) => (showRemoved || !item.removed) && `${item.name} ${item.owner_name} ${item.purity} ${item.seller ?? ""} ${item.notes}`.toLocaleLowerCase("en-IN").includes(search));
}

// Keep paise intact even for values above JavaScript's safe integer range.
export function goldAmount(value: string | null): string {
  if (value === null) return "—";
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(value);
  if (!match) return "—";
  const whole = new Intl.NumberFormat("en-IN").format(BigInt(match[2]));
  const fraction = (match[3] ?? "").padEnd(2, "0");
  return `${match[1]}₹${whole}${fraction === "00" ? "" : `.${fraction}`}`;
}
