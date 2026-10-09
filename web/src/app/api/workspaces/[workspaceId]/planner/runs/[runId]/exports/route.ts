import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

export async function POST(request: NextRequest, context: { params: Promise<{ workspaceId: string; runId: string }> }) {
  const { workspaceId, runId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(runId)) return NextResponse.json({ message: "Invalid plan." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/planner/runs/${runId}/exports/`, "POST");
}
