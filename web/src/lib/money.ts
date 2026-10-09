export function formatInr(value: string | number): string {
  const amount = Number(value);
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function balanceActionLabel(operation: "ADD" | "REMOVE" | "SET" | "ALLOTMENT"): string {
  if (operation === "ADD") return "+ Add Money";
  if (operation === "REMOVE") return "- Remove Money";
  if (operation === "ALLOTMENT") return "Allotment cost";
  return "Set Balance";
}
