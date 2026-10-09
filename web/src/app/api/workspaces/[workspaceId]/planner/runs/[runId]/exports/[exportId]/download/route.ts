import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

export async function GET(request: NextRequest, context: { params: Promise<{ workspaceId: string; runId: string; exportId: string }> }) {
  const { workspaceId, runId, exportId } = await context.params;
  if (![workspaceId, runId, exportId].every(isUuid)) return NextResponse.json({ message: "Invalid export." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/planner/runs/${runId}/exports/${exportId}/download/`, "GET");
}
