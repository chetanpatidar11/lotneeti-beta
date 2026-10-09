import { NextRequest, NextResponse } from "next/server";
import { copyAuthCookies } from "@/lib/auth-cookies";
import { backendUrl } from "@/lib/backend";

export async function POST(request: NextRequest) {
  const csrfToken = request.cookies.get("csrftoken")?.value;
  const url = backendUrl("auth/logout/");
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        cookie: request.headers.get("cookie") ?? "",
        origin: new URL(url).origin,
        ...(csrfToken ? { "x-csrftoken": csrfToken } : {}),
      },
      cache: "no-store",
    });
    if (!response.ok) return NextResponse.json({ message: "Sign-out failed." }, { status: 503 });
    const result = new NextResponse(null, { status: 204 });
    copyAuthCookies(response, result);
    return result;
  } catch {
    return NextResponse.json({ message: "Sign-out failed." }, { status: 503 });
  }
}
