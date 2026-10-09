import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ workspaceId: string }> },
) {
  const { workspaceId } = await context.params;
  if (!isUuid(workspaceId)) {
    return NextResponse.json({ message: "Invalid workspace." }, { status: 400 });
  }
  return proxyWorkspaceRequest(
    request,
    `workspaces/${workspaceId}/planner/validate/`,
    "POST",
  );
}
