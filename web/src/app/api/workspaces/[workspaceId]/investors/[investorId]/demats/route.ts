import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; investorId: string }> };

function path(workspaceId: string, investorId: string) {
  return `workspaces/${workspaceId}/investors/${investorId}/demats/`;
}

export async function GET(request: NextRequest, context: Context) {
  const { workspaceId, investorId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(investorId)) {
    return NextResponse.json({ message: "Invalid investor." }, { status: 400 });
  }
  return proxyWorkspaceRequest(request, path(workspaceId, investorId), "GET");
}

export async function POST(request: NextRequest, context: Context) {
  const { workspaceId, investorId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(investorId)) {
    return NextResponse.json({ message: "Invalid investor." }, { status: 400 });
  }
  return proxyWorkspaceRequest(request, path(workspaceId, investorId), "POST");
}