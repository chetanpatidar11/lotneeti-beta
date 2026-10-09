import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; importId: string }> };

export async function GET(request: NextRequest, context: Context) {
  const { workspaceId, importId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(importId)) return NextResponse.json({ message: "Invalid import." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/account-imports/${importId}/`, "GET");
}

export async function POST(request: NextRequest, context: Context) {
  const { workspaceId, importId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(importId)) return NextResponse.json({ message: "Invalid import." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/account-imports/${importId}/`, "POST");
}
