import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; ipoId: string }> };

export async function PATCH(request: NextRequest, context: Context) {
  const { workspaceId, ipoId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(ipoId)) return NextResponse.json({ message: "Invalid IPO." }, { status: 400 });
  return proxyWorkspaceRequest(request, `workspaces/${workspaceId}/ipo-decisions/${ipoId}/`, "PATCH");
}
