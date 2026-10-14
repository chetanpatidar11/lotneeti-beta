import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; investorId: string; dematId: string }> };

export async function GET(request: NextRequest, context: Context) {
  const { workspaceId, investorId, dematId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(investorId) || !isUuid(dematId)) return NextResponse.json({ message: "Invalid demat account." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/investors/${investorId}/demats/${dematId}/`, "GET");
}

export async function PATCH(request: NextRequest, context: Context) {
  const { workspaceId, investorId, dematId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(investorId) || !isUuid(dematId)) {
    return NextResponse.json({ message: "Invalid demat account." }, { status: 400 });
  }
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/investors/${investorId}/demats/${dematId}/`, "PATCH");
}
