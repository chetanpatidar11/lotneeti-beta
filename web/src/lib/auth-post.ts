import { NextResponse } from "next/server";
import { copyAuthCookies } from "./auth-cookies";
import { AUTH_REQUEST_HEADER } from "./auth-request";
import { frontendBaseUrl } from "./backend";
import { authTransport } from "./auth-transport";
import { privateAuthPost } from "./private-auth-post";

export async function authPost(request: Request, path: string, withCookies = false): Promise<NextResponse> {
  const origin = new URL(frontendBaseUrl).origin;
  const requestOrigin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  const contentType = request.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
  if (
    (requestOrigin !== null && requestOrigin !== origin) ||
    (fetchSite !== null && !["same-origin", "none"].includes(fetchSite)) ||
    request.headers.get(AUTH_REQUEST_HEADER) !== "1" ||
    contentType !== "application/json"
  ) {
    return NextResponse.json({ message: "Invalid request origin." }, { status: 403 });
  }
  try {
    const transport = authTransport(path, request.headers.get("x-real-ip"));
    const body = await request.text();
    const response = process.env.NODE_ENV === "production"
      ? await privateAuthPost(transport.url, transport.headers, body)
      : await fetch(transport.url, {
        method: "POST",
        headers: transport.headers,
        body,
        cache: "no-store",
        redirect: "error",
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
