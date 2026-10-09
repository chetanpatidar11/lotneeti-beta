import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

export async function POST(request: NextRequest, context: { params: Promise<{ workspaceId: string; applicationId: string; action: string }> }) {
  const { workspaceId, applicationId, action } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(applicationId) || !["submit", "block", "not-allotted", "allotted"].includes(action)) return NextResponse.json({ message: "Invalid application action." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/applications/${applicationId}/${action}/`, "POST");
}
