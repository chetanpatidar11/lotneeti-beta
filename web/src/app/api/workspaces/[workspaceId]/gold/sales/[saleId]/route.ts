import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; saleId: string }> };

export async function PATCH(request: NextRequest, context: Context) {
  const { workspaceId, saleId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(saleId)) return NextResponse.json({ detail: "Invalid gold record." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/gold/sales/${saleId}/`, "PATCH");
}

export async function DELETE(request: NextRequest, context: Context) {
  const { workspaceId, saleId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(saleId)) return NextResponse.json({ detail: "Invalid gold record." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/gold/sales/${saleId}/`, "DELETE");
}

export async function POST(request: NextRequest, context: Context) {
  const { workspaceId, saleId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(saleId)) return NextResponse.json({ detail: "Invalid gold record." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/gold/sales/${saleId}/`, "POST");
}
