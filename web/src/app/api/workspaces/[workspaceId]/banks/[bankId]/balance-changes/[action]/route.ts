import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; bankId: string; action: string }> };

export async function POST(request: NextRequest, context: Context) {
  const { workspaceId, bankId, action } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(bankId) || !["add", "remove", "set"].includes(action)) {
    return NextResponse.json({ message: "Invalid balance action." }, { status: 400 });
  }
  return proxyWorkspaceRequest(
    request,
    `workspaces/${workspaceId}/banks/${bankId}/balance-changes/${action}/`,
    "POST",
  );
}
