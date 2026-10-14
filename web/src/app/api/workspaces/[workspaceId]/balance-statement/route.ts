import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

export async function GET(request: NextRequest, context: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await context.params;
  if (!isUuid(workspaceId)) return NextResponse.json({ message: "Invalid workspace." }, { status: 400 });
  const page = request.nextUrl.searchParams.get("page") ?? "1";
  const bank = request.nextUrl.searchParams.get("bank") ?? "";
  if (!/^[1-9]\d*$/.test(page) || (bank && !isUuid(bank))) {
    return NextResponse.json({ message: "Invalid statement filter." }, { status: 400 });
  }
  const params = new URLSearchParams({ page });
  if (bank) params.set("bank", bank);
  return proxyWorkspaceRequest(
    request, `workspaces/${workspaceId}/balance-statement/?${params}`, "GET",
  );
}
