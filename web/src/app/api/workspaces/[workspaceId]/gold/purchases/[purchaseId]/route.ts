import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; purchaseId: string }> };

export async function PATCH(request: NextRequest, context: Context) {
  const { workspaceId, purchaseId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(purchaseId)) return NextResponse.json({ detail: "Invalid gold record." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/gold/purchases/${purchaseId}/`, "PATCH");
}

export async function DELETE(request: NextRequest, context: Context) {
  const { workspaceId, purchaseId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(purchaseId)) return NextResponse.json({ detail: "Invalid gold record." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/gold/purchases/${purchaseId}/`, "DELETE");
}

export async function POST(request: NextRequest, context: Context) {
  const { workspaceId, purchaseId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(purchaseId)) return NextResponse.json({ detail: "Invalid gold record." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/gold/purchases/${purchaseId}/`, "POST");
}
