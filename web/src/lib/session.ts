import { cookies } from "next/headers";
import { backendUrl } from "./backend";

type CurrentUser = { id: number; email: string };

export async function getCurrentUser(): Promise<CurrentUser | null> {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader.includes("sessionid=")) return null;

  try {
    const response = await fetch(backendUrl("me/"), {
      headers: { cookie: cookieHeader },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as CurrentUser;
  } catch {
    return null;
  }
}
