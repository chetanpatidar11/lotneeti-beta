import { NextRequest, NextResponse } from "next/server";
import { backendUrl, frontendBaseUrl } from "./backend";

export function trustedWorkspaceMutation(request: Request): boolean {
  const origin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  return (
    (origin === new URL(frontendBaseUrl).origin || (origin === null && fetchSite === "same-origin")) &&
    (fetchSite === null || ["same-origin", "none"].includes(fetchSite))
  );
}

export async function proxyWorkspaceRequest(
  request: NextRequest,
  path: string,
  method: "GET" | "POST" | "PATCH" | "DELETE",
): Promise<NextResponse> {
  if (method !== "GET" && !trustedWorkspaceMutation(request)) {
    return NextResponse.json({ message: "Invalid request origin." }, { status: 403 });
  }
  const url = backendUrl(path);
  const csrfToken = request.cookies.get("csrftoken")?.value;
  try {
    const response = await fetch(url, {
      method,
      headers: {
        cookie: request.headers.get("cookie") ?? "",
        origin: new URL(url).origin,
        ...(method === "GET" || method === "DELETE" ? {} : { "content-type": "application/json" }),
        ...(csrfToken ? { "x-csrftoken": csrfToken } : {}),
      },
      ...(method === "GET" || method === "DELETE" ? {} : { body: await request.text() }),
      cache: "no-store",
    });
    if (response.status === 204) return new NextResponse(null, { status: 204, headers: { "cache-control": "no-store" } });
    return new NextResponse(await response.arrayBuffer(), {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json",
        "cache-control": "private, no-store",
        "x-content-type-options": "nosniff",
        ...(response.headers.has("content-disposition") ? { "content-disposition": response.headers.get("content-disposition")! } : {}),
      },
    });
  } catch {
    return NextResponse.json({ message: "Service is temporarily unavailable." }, { status: 503 });
  }
}

export async function proxyWorkspaceUpload(
  request: NextRequest,
  path: string,
): Promise<NextResponse> {
  if (!trustedWorkspaceMutation(request)) {
    return NextResponse.json({ message: "Invalid request origin." }, { status: 403 });
  }
  const url = backendUrl(path);
  const csrfToken = request.cookies.get("csrftoken")?.value;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        cookie: request.headers.get("cookie") ?? "",
        origin: new URL(url).origin,
        ...(csrfToken ? { "x-csrftoken": csrfToken } : {}),
      },
      body: await request.formData(),
      cache: "no-store",
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch {
    return NextResponse.json({ message: "Import is temporarily unavailable." }, { status: 503 });
  }
}

export function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
