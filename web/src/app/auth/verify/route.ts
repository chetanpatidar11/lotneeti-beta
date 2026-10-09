import { NextRequest, NextResponse } from "next/server";
import { copyAuthCookies } from "@/lib/auth-cookies";
import { backendUrl, frontendBaseUrl } from "@/lib/backend";

export async function GET(request: NextRequest) {
  const token = request.nextUrl.searchParams.get("token");
  if (!token) return NextResponse.redirect(new URL("/sign-in?error=link", frontendBaseUrl));

  try {
    const response = await fetch(backendUrl("auth/email/verify/"), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(request.headers.get("x-real-ip") ? { "x-real-ip": request.headers.get("x-real-ip")! } : {}),
      },
      body: JSON.stringify({ token }),
      cache: "no-store",
    });
    if (!response.ok) return NextResponse.redirect(new URL("/sign-in?error=link", frontendBaseUrl));

    const redirect = NextResponse.redirect(new URL("/", frontendBaseUrl));
    copyAuthCookies(response, redirect);
    redirect.headers.set("referrer-policy", "no-referrer");
    redirect.headers.set("cache-control", "no-store");
    return redirect;
  } catch {
    return NextResponse.redirect(new URL("/sign-in?error=link", frontendBaseUrl));
  }
}
