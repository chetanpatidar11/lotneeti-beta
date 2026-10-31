import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";
type Context = { params: Promise<{ workspaceId: string }> };
async function proxy(request: NextRequest, context: Context, method: "GET" | "POST") {
  const { workspaceId } = await context.params;
  if (!isUuid(workspaceId)) return NextResponse.json({ message: "Invalid account." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/allotment/checks/`, method);
}
export async function GET(request: NextRequest, context: Context) { return proxy(request, context, "GET"); }
export async function POST(request: NextRequest, context: Context) { return proxy(request, context, "POST"); }
