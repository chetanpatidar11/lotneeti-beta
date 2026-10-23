import { NextRequest } from "next/server";
import { proxyWorkspaceRequest } from "@/lib/proxy";

export async function GET(request: NextRequest) {
  return proxyWorkspaceRequest(request, "workspaces/", "GET");
}
