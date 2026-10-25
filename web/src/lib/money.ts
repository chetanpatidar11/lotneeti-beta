export function formatInr(value: string | number): string {
  const amount = Number(value);
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function balanceActionLabel(operation: "ADD" | "REMOVE" | "SET" | "TRANSFER_OUT" | "TRANSFER_IN" | "ALLOTMENT"): string {
  if (operation === "ADD") return "+ Add Money";
  if (operation === "REMOVE") return "- Remove Money";
  if (operation === "ALLOTMENT") return "Allotment cost";
  if (operation === "TRANSFER_OUT") return "Transfer to bank";
  if (operation === "TRANSFER_IN") return "Transfer from bank";
  return "Set Balance";
}


type InrValue = string | number | null | undefined;

function inrPaise(value: InrValue): bigint {
  const match = String(value ?? "0").trim().match(/^(-?)(\d+)(?:\.(\d{1,2}))?$/);
  if (!match) return 0n;
  const paise = BigInt(match[2]) * 100n + BigInt((match[3] ?? "").padEnd(2, "0") || "0");
  return match[1] ? -paise : paise;
}

export function sumInr(values: InrValue[]): number {
  const totalPaise = values.reduce<bigint>((sum, value) => sum + inrPaise(value), 0n);
  return Number(totalPaise) / 100;
}

export function availableInr(balance: InrValue, blocked: InrValue, planned: InrValue): number {
  const netPaise = inrPaise(balance) - inrPaise(blocked) - inrPaise(planned);
  return Number(netPaise > 0n ? netPaise : 0n) / 100;
}
