import { NextRequest, NextResponse } from "next/server";
import { frontendBaseUrl } from "@/lib/backend";
import { AUTH_REQUEST_HEADER } from "@/lib/auth-request";
import { proxyWorkspaceRequest } from "@/lib/proxy";

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  const site = request.headers.get("sec-fetch-site");
  if (
    (origin !== null && origin !== new URL(frontendBaseUrl).origin) ||
    (site !== null && !["same-origin", "none"].includes(site)) ||
    request.headers.get(AUTH_REQUEST_HEADER) !== "1" ||
    request.headers.get("content-type")?.split(";", 1)[0] !== "application/json"
  ) {
    return NextResponse.json({ message: "Invalid request origin." }, { status: 403 });
  }
  return proxyWorkspaceRequest(request, "ipos/live-sync/", "POST");
}
