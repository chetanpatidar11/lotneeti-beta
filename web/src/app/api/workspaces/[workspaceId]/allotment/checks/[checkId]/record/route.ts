import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";
export async function POST(request: NextRequest, context: { params: Promise<{ workspaceId: string; checkId: string }> }) {
  const { workspaceId, checkId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(checkId)) return NextResponse.json({ message: "Invalid check." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/allotment/checks/${checkId}/record/`, "POST");
}
