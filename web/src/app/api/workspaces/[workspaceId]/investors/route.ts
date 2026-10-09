import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string }> };

export async function GET(request: NextRequest, context: Context) {
  const { workspaceId } = await context.params;
  if (!isUuid(workspaceId)) return NextResponse.json({ message: "Invalid workspace." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/investors/`, "GET");
}

export async function POST(request: NextRequest, context: Context) {
  const { workspaceId } = await context.params;
  if (!isUuid(workspaceId)) return NextResponse.json({ message: "Invalid workspace." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/investors/`, "POST");
}
