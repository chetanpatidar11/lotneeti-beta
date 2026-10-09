import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; investorId: string; preferenceId: string }> };

function path(workspaceId: string, investorId: string, preferenceId: string) {
  return `workspaces/${workspaceId}/investors/${investorId}/funding-preferences/${preferenceId}/`;
}

export async function PATCH(request: NextRequest, context: Context) {
  const { workspaceId, investorId, preferenceId } = await context.params;
  if (![workspaceId, investorId, preferenceId].every(isUuid)) return NextResponse.json({ message: "Invalid preference." }, { status: 400 });
  return proxyWorkspaceRequest(request, path(workspaceId, investorId, preferenceId), "PATCH");
}

export async function DELETE(request: NextRequest, context: Context) {
  const { workspaceId, investorId, preferenceId } = await context.params;
  if (![workspaceId, investorId, preferenceId].every(isUuid)) return NextResponse.json({ message: "Invalid preference." }, { status: 400 });
  return proxyWorkspaceRequest(request, path(workspaceId, investorId, preferenceId), "DELETE");
}
