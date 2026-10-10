import { NextRequest, NextResponse } from "next/server";
import { copyAuthCookies } from "@/lib/auth-cookies";
import { backendUrl } from "@/lib/backend";

export async function POST(request: NextRequest) {
  if (!request.cookies.has("sessionid")) return new NextResponse(null, { status: 401 });
  try {
    const url = backendUrl("auth/session/refresh/");
    const response = await fetch(url, {
      method: "POST",
      headers: {
        cookie: request.headers.get("cookie") ?? "",
        origin: new URL(url).origin,
        ...(request.cookies.get("csrftoken")?.value
          ? { "x-csrftoken": request.cookies.get("csrftoken")!.value }
          : {}),
      },
      cache: "no-store",
    });
    if (!response.ok) return new NextResponse(null, { status: 401 });
    const result = new NextResponse(null, { status: 204, headers: { "cache-control": "no-store" } });
    copyAuthCookies(response, result);
    return result;
  } catch {
    return new NextResponse(null, { status: 503 });
  }
}
