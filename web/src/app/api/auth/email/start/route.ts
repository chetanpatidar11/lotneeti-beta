import { NextResponse } from "next/server";
import { backendUrl } from "@/lib/backend";

export async function POST(request: Request) {
  try {
    const response = await fetch(backendUrl("auth/email/start/"), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(request.headers.get("x-real-ip") ? { "x-real-ip": request.headers.get("x-real-ip")! } : {}),
      },
      body: await request.text(),
      cache: "no-store",
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json({ message: "Sign-in is temporarily unavailable." }, { status: 503 });
  }
}
