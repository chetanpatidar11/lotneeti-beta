import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; bankId: string; upiId: string }> };

export async function PATCH(request: NextRequest, context: Context) {
  const { workspaceId, bankId, upiId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(bankId) || !isUuid(upiId)) {
    return NextResponse.json({ message: "Invalid UPI ID." }, { status: 400 });
  }
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/banks/${bankId}/upis/${upiId}/`, "PATCH");
}
