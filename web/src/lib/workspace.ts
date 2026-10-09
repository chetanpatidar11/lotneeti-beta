import { cookies } from "next/headers";

export async function selectedWorkspace<T extends { id: string }>(items: T[]): Promise<T | undefined> {
  const selected = (await cookies()).get("lotneeti_workspace")?.value;
  return items.find((item) => item.id === selected) ?? items[0];
}
