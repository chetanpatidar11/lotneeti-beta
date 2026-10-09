import { NextResponse } from "next/server";

export function copyAuthCookies(source: Response, target: NextResponse): void {
  for (const cookie of source.headers.getSetCookie()) {
    target.headers.append("set-cookie", cookie);
  }
}
