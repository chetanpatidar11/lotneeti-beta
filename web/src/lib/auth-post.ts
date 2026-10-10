import { NextResponse } from "next/server";
import { copyAuthCookies } from "./auth-cookies";
import { backendUrl, frontendBaseUrl } from "./backend";

export async function authPost(request: Request, path: string, withCookies = false): Promise<NextResponse> {
  const origin = new URL(frontendBaseUrl).origin;
  if (request.headers.get("origin") !== origin) {
    return NextResponse.json({ message: "Invalid request origin." }, { status: 403 });
  }
  try {
    const response = await fetch(backendUrl(path), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        origin,
        ...(request.headers.get("x-real-ip") ? { "x-real-ip": request.headers.get("x-real-ip")! } : {}),
      },
      body: await request.text(),
      cache: "no-store",
    });
    const result = new NextResponse(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
    if (withCookies && response.ok) copyAuthCookies(response, result);
    return result;
  } catch {
    return NextResponse.json({ message: "Sign-in is temporarily unavailable." }, { status: 503 });
  }
}
