import { NextRequest, NextResponse } from "next/server";
import { copyAuthCookies } from "@/lib/auth-cookies";
import { backendUrl, frontendBaseUrl } from "@/lib/backend";
import { localPreviewEnabled } from "@/lib/local-preview";

export async function GET(request: NextRequest) {
  if (!localPreviewEnabled() || !["localhost", "127.0.0.1", "::1"].includes(request.nextUrl.hostname)) {
    return new NextResponse(null, { status: 404 });
  }

  try {
    const response = await fetch(backendUrl("auth/local-preview/"), {
      method: "POST",
      headers: { origin: frontendBaseUrl.replace(/\/+$/, "") },
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Local preview sign-in failed");
    const redirect = NextResponse.redirect(new URL("/", frontendBaseUrl));
    copyAuthCookies(response, redirect);
    redirect.headers.set("cache-control", "no-store");
    return redirect;
  } catch {
    return NextResponse.redirect(new URL("/sign-in?error=local", frontendBaseUrl));
  }
}
