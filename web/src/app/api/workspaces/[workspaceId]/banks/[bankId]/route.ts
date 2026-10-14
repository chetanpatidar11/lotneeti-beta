import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; bankId: string }> };

export async function PATCH(request: NextRequest, context: Context) {
  const { workspaceId, bankId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(bankId)) {
    return NextResponse.json({ message: "Invalid bank." }, { status: 400 });
  }
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/banks/${bankId}/`, "PATCH");
}
