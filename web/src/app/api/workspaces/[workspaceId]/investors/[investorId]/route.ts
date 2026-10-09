import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; investorId: string }> };

export async function PATCH(request: NextRequest, context: Context) {
  const { workspaceId, investorId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(investorId)) {
    return NextResponse.json({ message: "Invalid investor." }, { status: 400 });
  }
  return proxyWorkspaceRequest(
    request,
    `workspaces/${workspaceId}/investors/${investorId}/`,
    "PATCH",
  );
}
